#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API 健康度檢測腳本 - 第二階段
從第一階段的 JSON 記錄檔讀取 API 呼叫資訊，批次執行並驗證結果
"""

import json
import requests
import time
import urllib3
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 禁用 SSL 警告（測試環境可能使用自簽憑證）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class ApiTestResult:
    """單一 API 測試結果"""
    endpoint: str
    method: str
    expected_status: int
    actual_status: int
    response_time_ms: float
    is_success: bool
    test_strategy: str = "full_call"
    response_body: Any = None
    error_message: str = ""
    validation_errors: List[str] = field(default_factory=list)
    request_params: Dict = field(default_factory=dict)


@dataclass
class HealthReport:
    """健康度報告"""
    test_date: str
    environment: str
    total_apis: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_response_time_ms: float = 0.0
    health_score: float = 0.0
    results: List[ApiTestResult] = field(default_factory=list)
    critical_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ApiHealthTester:
    """API 健康度測試器"""

    def __init__(self, config_path: str, parallel_workers: int = 1):
        """初始化測試器
        
        Args:
            config_path: 設定檔路徑
            parallel_workers: 並行執行緒數量 (預設 1 = 序列執行)
        """
        self.config = self._load_config(config_path)
        self.base_url = self.config.get("base_url", "")
        self.token: Optional[str] = None
        self.session = requests.Session()
        self.parallel_workers = parallel_workers

        # 從 config 讀取 SLA 閾值，預設 10000ms（ABP 專案第一次呼叫較慢）
        self.sla_threshold_ms = self.config.get("sla_threshold_ms", 10000)

        # 禁用 SSL 憑證驗證（測試環境可能使用自簽憑證）
        self.session.verify = False

        # 設定預設 headers
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "API-Health-Tester/1.0",
            "X-Requested-With": "XMLHttpRequest"  # 模擬 AJAX 請求
        })

    def _load_config(self, config_path: str) -> Dict:
        """載入設定檔"""
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def login(self) -> bool:
        """執行登入取得 Token"""
        login_url = f"{self.base_url}/api/app/users/Login"
        login_data = {
            "TenantName": self.config["tenant"],
            "LoginId": self.config["account"],
            "Password": self.config["password"]
        }

        try:
            print(f"[登入] 正在登入 {self.config['tenant']} / {self.config['account']}...")
            response = self.session.post(login_url, json=login_data, timeout=30)

            if response.status_code == 200:
                data = response.json()
                # 嘗試多種 token 結構
                self.token = (
                    data.get("accessToken") or
                    data.get("access_token") or
                    (data.get("id4Token", {}).get("access_token"))
                )
                if self.token:
                    self.session.headers["Authorization"] = f"Bearer {self.token}"
                    print(f"[登入] 成功取得 Token")
                    
                    # 取得使用者資訊以獲取 orgEmpCode
                    self._fetch_user_info()
                    
                    return True
                else:
                    print(f"[登入] 響應中找不到 Token: {data}")
                    return False
            else:
                print(f"[登入] 失敗 - 狀態碼: {response.status_code}")
                return False

        except Exception as e:
            print(f"[登入] 錯誤: {str(e)}")
            return False

    def _fetch_user_info(self):
        """取得登入使用者資訊"""
        try:
            user_info_url = f"{self.base_url}/api/app/share/GetUserInfo"
            response = self.session.get(user_info_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                self.org_emp_code = data.get("orgEmpCode", "")
                print(f"[使用者] orgEmpCode: {self.org_emp_code}")
            else:
                print(f"[使用者] 無法取得使用者資訊: {response.status_code}")
                self.org_emp_code = ""
        except Exception as e:
            print(f"[使用者] 取得使用者資訊錯誤: {str(e)}")
            self.org_emp_code = ""

    def _replace_dynamic_params(self, params: Dict) -> Dict:
        """替換請求參數中的動態標記"""
        if not params:
            return params
        
        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                # 替換使用者員工代碼標記
                if value == "***USE_LOGGED_IN_USER_EMP_CODE***":
                    result[key] = getattr(self, 'org_emp_code', '')
                else:
                    result[key] = value
            elif isinstance(value, dict):
                result[key] = self._replace_dynamic_params(value)
            elif isinstance(value, list):
                result[key] = [
                    self._replace_dynamic_params(item) if isinstance(item, dict)
                    else (getattr(self, 'org_emp_code', '') if item == "***USE_LOGGED_IN_USER_EMP_CODE***" else item)
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def _mask_sensitive_params(self, params: Dict) -> Dict:
        """遮蔽敏感參數"""
        if not params:
            return params
        
        sensitive_keys = ["password", "Password", "token", "Token", "secret", "Secret", "key", "Key"]
        result = {}
        for k, v in params.items():
            if any(sensitive in k for sensitive in sensitive_keys):
                result[k] = "***MASKED***"
            elif isinstance(v, dict):
                result[k] = self._mask_sensitive_params(v)
            else:
                result[k] = v
        return result

    def test_api(self, api_info: Dict) -> ApiTestResult:
        """測試單一 API"""
        endpoint = api_info.get("endpoint", "")
        full_url = api_info.get("fullUrl", "")
        method = api_info.get("method", "GET").upper()
        expected_status = api_info.get("expectedStatus", 200)
        request_params = api_info.get("requestParams", {}).copy()  # 複製避免修改原始資料
        expected_response = api_info.get("actualResponse", {})
        test_strategy = api_info.get("testStrategy", "full_call")

        # 替換動態參數
        request_params = self._replace_dynamic_params(request_params)

        # 過濾掉敏感資料
        if "Password" in request_params:
            request_params = {**request_params, "Password": self.config.get("password", "")}

        start_time = time.time()

        try:
            if method == "GET":
                response = self.session.get(full_url, params=request_params, timeout=30)
            elif method == "POST":
                response = self.session.post(full_url, json=request_params, timeout=30)
            elif method == "PUT":
                response = self.session.put(full_url, json=request_params, timeout=30)
            elif method == "DELETE":
                response = self.session.delete(full_url, timeout=30)
            else:
                response = self.session.request(method, full_url, json=request_params, timeout=30)

            response_time_ms = (time.time() - start_time) * 1000
            actual_status = response.status_code

            try:
                response_body = response.json()
            except:
                response_body = response.text

            # 根據測試策略驗證結果
            validation_errors = []
            
            if test_strategy == "liveness_probe":
                # 存活性探測：400 或 422 視為成功
                is_success = actual_status in [400, 422]
                if not is_success:
                    validation_errors.append(f"存活性探測預期 400/422，實際為 {actual_status}")
            else:
                # full_call：預期狀態碼必須完全相符
                is_success = actual_status == expected_status

            # 檢查回應時間
            if response_time_ms > self.sla_threshold_ms:
                validation_errors.append(f"回應時間 {response_time_ms:.0f}ms 超過 SLA 閾值 {self.sla_threshold_ms}ms")

            # 檢查響應結構 (僅 full_call 策略)
            if test_strategy == "full_call" and isinstance(expected_response, dict) and isinstance(response_body, dict):
                for key in expected_response.keys():
                    if key not in ["note", "items"] and key not in response_body:
                        validation_errors.append(f"響應缺少欄位: {key}")

            # 過濾敏感資料用於報告輸出
            safe_params = self._mask_sensitive_params(request_params)

            return ApiTestResult(
                endpoint=endpoint,
                method=method,
                expected_status=expected_status,
                actual_status=actual_status,
                response_time_ms=response_time_ms,
                is_success=is_success and len(validation_errors) == 0,
                test_strategy=test_strategy,
                response_body=response_body,
                validation_errors=validation_errors,
                request_params=safe_params
            )

        except requests.exceptions.Timeout:
            safe_params = self._mask_sensitive_params(request_params)
            return ApiTestResult(
                endpoint=endpoint,
                method=method,
                expected_status=expected_status,
                actual_status=0,
                response_time_ms=(time.time() - start_time) * 1000,
                is_success=False,
                error_message="請求超時",
                request_params=safe_params
            )
        except Exception as e:
            safe_params = self._mask_sensitive_params(request_params)
            return ApiTestResult(
                endpoint=endpoint,
                method=method,
                expected_status=expected_status,
                actual_status=0,
                response_time_ms=(time.time() - start_time) * 1000,
                is_success=False,
                error_message=str(e),
                request_params=safe_params
            )

    def run_tests(self, api_record_path: str) -> HealthReport:
        """執行所有 API 測試"""
        # 載入 API 記錄
        with open(api_record_path, "r", encoding="utf-8") as f:
            api_record = json.load(f)

        test_info = api_record.get("testInfo", {})
        page_flows = api_record.get("pageFlows", [])

        report = HealthReport(
            test_date=datetime.now().isoformat(),
            environment=test_info.get("environment", "")
        )

        # 先執行登入
        if not self.login():
            report.critical_failures.append("登入失敗，無法繼續測試")
            return report

        total_response_time = 0.0

        # 收集所有需要測試的 API
        apis_to_test = []
        for flow in page_flows:
            flow_name = flow.get("pageFlow", "")
            api_calls = flow.get("apiCalls", [])

            for api in api_calls:
                endpoint = api.get("endpoint", "")
                test_strategy = api.get("testStrategy", "full_call")

                # 跳過登入 API (已經執行過)
                if "Login" in endpoint:
                    continue

                # 跳過預期失敗的 API (如 401)
                if api.get("expectedStatus") in [302, 401]:
                    continue

                # 跳過 skip 策略的 API
                if test_strategy == "skip":
                    print(f"  [SKIP] {api.get('method', 'GET')} {endpoint}")
                    continue

                apis_to_test.append((flow_name, api))

        print(f"\n[測試] 共收集 {len(apis_to_test)} 個 API 待測試")
        
        # 並行執行測試
        if self.parallel_workers > 1:
            print(f"[測試] 使用 {self.parallel_workers} 個並行執行緒")
            report = self._run_tests_parallel(apis_to_test, report)
        else:
            print("[測試] 使用序列模式執行")
            report = self._run_tests_sequential(apis_to_test, report)

        return report

    def _run_tests_sequential(self, apis_to_test: List, report: HealthReport) -> HealthReport:
        """序列執行測試"""
        total_response_time = 0.0
        current_flow = ""

        for flow_name, api in apis_to_test:
            if flow_name != current_flow:
                print(f"\n[測試] 頁面流程: {flow_name}")
                print("-" * 50)
                current_flow = flow_name

            result = self.test_api(api)
            report.results.append(result)
            report.total_apis += 1
            total_response_time += result.response_time_ms

            self._print_result(result, report)

        # 計算統計
        if report.total_apis > 0:
            report.avg_response_time_ms = total_response_time / report.total_apis
            report.health_score = (report.success_count / report.total_apis) * 100

        return report

    def _run_tests_parallel(self, apis_to_test: List, report: HealthReport) -> HealthReport:
        """並行執行測試"""
        total_response_time = 0.0
        results_lock = threading.Lock()
        print_lock = threading.Lock()

        def test_single_api(flow_api_tuple):
            flow_name, api = flow_api_tuple
            result = self.test_api(api)
            return flow_name, result

        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            futures = {executor.submit(test_single_api, item): item for item in apis_to_test}
            
            for future in as_completed(futures):
                try:
                    flow_name, result = future.result()
                    
                    with results_lock:
                        report.results.append(result)
                        report.total_apis += 1
                        total_response_time += result.response_time_ms
                    
                    with print_lock:
                        self._print_result(result, report)

                except Exception as e:
                    print(f"  [ERROR] 測試執行錯誤: {str(e)}")

        # 計算統計
        if report.total_apis > 0:
            report.avg_response_time_ms = total_response_time / report.total_apis
            report.health_score = (report.success_count / report.total_apis) * 100

        return report

    def _print_result(self, result: ApiTestResult, report: HealthReport):
        """列印單一測試結果"""
        status_icon = "[OK]" if result.is_success else "[FAIL]"
        strategy_label = f"[{result.test_strategy}]" if result.test_strategy != "full_call" else ""
        print(f"  {status_icon} {result.method} {result.endpoint} {strategy_label}")
        print(f"    狀態: {result.actual_status} (預期: {result.expected_status})")
        print(f"    回應時間: {result.response_time_ms:.0f}ms")

        if result.is_success:
            report.success_count += 1
        else:
            report.failure_count += 1
            if result.error_message:
                print(f"    錯誤: {result.error_message}")
                report.critical_failures.append(f"{result.endpoint}: {result.error_message}")
            for err in result.validation_errors:
                print(f"    警告: {err}")
                report.warnings.append(f"{result.endpoint}: {err}")

    def generate_report(self, report: HealthReport, output_path: str):
        """產生報告檔案"""
        report_data = {
            "testDate": report.test_date,
            "environment": report.environment,
            "summary": {
                "totalApis": report.total_apis,
                "successCount": report.success_count,
                "failureCount": report.failure_count,
                "avgResponseTimeMs": round(report.avg_response_time_ms, 2),
                "healthScore": f"{report.health_score:.1f}%"
            },
            "criticalFailures": report.critical_failures,
            "warnings": report.warnings,
            "detailedResults": [
                {
                    "endpoint": r.endpoint,
                    "method": r.method,
                    "testStrategy": r.test_strategy,
                    "expectedStatus": r.expected_status,
                    "actualStatus": r.actual_status,
                    "responseTimeMs": round(r.response_time_ms, 2),
                    "isSuccess": r.is_success,
                    "errorMessage": r.error_message,
                    "validationErrors": r.validation_errors,
                    "requestParams": r.request_params
                }
                for r in report.results
            ]
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

        print(f"\n[報告] 已儲存至: {output_path}")

    def print_summary(self, report: HealthReport):
        """列印摘要"""
        print("\n" + "=" * 60)
        print("API 健康度檢測報告")
        print("=" * 60)
        print(f"測試時間: {report.test_date}")
        print(f"測試環境: {report.environment}")
        print("-" * 60)
        print(f"總 API 數量:     {report.total_apis}")
        print(f"成功:            {report.success_count}")
        print(f"失敗:            {report.failure_count}")
        print(f"平均回應時間:    {report.avg_response_time_ms:.0f}ms")
        print(f"健康度評分:      {report.health_score:.1f}%")
        print("-" * 60)

        if report.critical_failures:
            print("\n[Critical] 嚴重問題:")
            for failure in report.critical_failures:
                print(f"  - {failure}")

        if report.warnings:
            print("\n[Warning] 警告:")
            for warning in report.warnings:
                print(f"  - {warning}")

        if not report.critical_failures and not report.warnings:
            print("\n[OK] 所有 API 運作正常!")

        print("=" * 60)


def main():
    """主程式"""
    import argparse

    parser = argparse.ArgumentParser(description="API 健康度檢測腳本")
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="設定檔路徑 (預設: config.json)"
    )
    parser.add_argument(
        "--record", "-r",
        default="api-health-report.json",
        help="API 記錄檔路徑 (預設: api-health-report.json)"
    )
    parser.add_argument(
        "--output", "-o",
        default="test-result.json",
        help="輸出報告路徑 (預設: test-result.json)"
    )
    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=1,
        help="並行執行緒數量 (預設: 1 = 序列執行，建議 5-10)"
    )

    args = parser.parse_args()

    # 取得腳本所在目錄
    script_dir = Path(__file__).parent
    config_path = script_dir / args.config
    record_path = script_dir / args.record
    output_path = script_dir / args.output

    print("=" * 60)
    print("API 健康度檢測腳本 - 第二階段")
    print("=" * 60)
    print(f"設定檔: {config_path}")
    print(f"API 記錄: {record_path}")
    print(f"輸出報告: {output_path}")
    print(f"並行執行緒: {args.parallel}")

    # 執行測試
    tester = ApiHealthTester(str(config_path), parallel_workers=args.parallel)
    report = tester.run_tests(str(record_path))

    # 產生報告
    tester.generate_report(report, str(output_path))
    tester.print_summary(report)

    # 回傳結束碼
    return 0 if report.failure_count == 0 else 1


if __name__ == "__main__":
    exit(main())
