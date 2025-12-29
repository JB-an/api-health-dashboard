# API 健康度檢測腳本 - 第二階段

## 說明

此腳本從第一階段錄製的 API 記錄檔中讀取所有 API 呼叫資訊，批次執行並驗證結果，最終產生健康度報告。

## 檔案結構

```
api-health-test/
├── api_health_test.py      # 主程式
├── config.json             # 設定檔（帳號密碼等）
├── api-health-report.json  # 第一階段錄製的 API 記錄
├── requirements.txt        # Python 依賴
└── README.md               # 說明文件
```

## 安裝

```bash
pip install -r requirements.txt
```

## 使用方式

### 基本執行

```bash
python api_health_test.py
```

### 自訂參數

```bash
python api_health_test.py --config config.json --record api-health-report.json --output test-result.json
```

### 參數說明

| 參數 | 簡寫 | 預設值 | 說明 |
|------|------|--------|------|
| --config | -c | config.json | 設定檔路徑 |
| --record | -r | api-health-report.json | API 記錄檔路徑 |
| --output | -o | test-result.json | 輸出報告路徑 |

## 設定檔 (config.json)

```json
{
  "base_url": "https://deploy.jbhr.com.tw/App/Test/Portal/PortalApi",
  "tenant": "Bossmen",
  "account": "1308",
  "password": "your_password",
  "sla_threshold_ms": 3000
}
```

## 輸出報告

執行後會產生 `test-result.json`，包含：

- **summary**: 總結統計（成功數、失敗數、平均回應時間、健康度評分）
- **criticalFailures**: 嚴重錯誤清單
- **warnings**: 警告清單（如回應時間超過 SLA）
- **detailedResults**: 每個 API 的詳細測試結果

## 健康度評分計算

```
健康度 = (成功 API 數量 / 總 API 數量) × 100%
```

## SLA 閾值

預設 API 回應時間 SLA 閾值為 3000ms，超過會產生警告。可在 `config.json` 中調整 `sla_threshold_ms`。

## 定期執行（排程）

### Windows 工作排程器

```cmd
schtasks /create /tn "API Health Check" /tr "python C:\path\to\api_health_test.py" /sc daily /st 09:00
```

### Linux Cron

```bash
0 9 * * * cd /path/to/api-health-test && python api_health_test.py >> /var/log/api-health.log 2>&1
```
