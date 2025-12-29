# AI 輔助的 API 健康度檢測系統

## 目標

透過 Claude Code 操作 Chrome 瀏覽器進行實際使用者介面互動，自動化記錄各頁面發起的 API 呼叫（包含請求參數和響應內容），並與預期結果進行對比驗證，以判定 API 健康狀態。相比傳統單元測試，此方案透過 AI 簡化人工測試用例建置的流程，降低測試維護成本。

## 核心步驟

### 第一階段：API 呼叫映射與錄製

1. **瀏覽器監控設定**

   - 使用 Claude Code 以瀏覽器開發者工具（DevTools）的 Network 標籤監控所有 HTTP/HTTPS 請求
   - 記錄以下資訊：
     - API 端點 URL（包含查詢參數）
     - HTTP 方法（GET、POST、PUT、DELETE 等）
     - 請求標頭（Header）中的認證令牌、Content-Type 等關鍵欄位
     - 請求本體（Request Body）的完整 JSON/表單資料
     - 響應狀態碼（Status Code）
     - 響應本體（Response Body）的完整內容
     - 回應時間（Duration）

2. **使用者操作流程**

   - 指示 Claude 依序操作各個關鍵使用者旅程（User Journey）
   - 例如：登入 → 瀏覽列表 → 編輯資料 → 提交表單 → 確認結果
   - 對於每個頁面狀態變化，確認所觸發的 API 呼叫集合

3. **記錄格式**

   - 輸出結構化的 JSON 檔案或 CSV 表格，包含：

     ```
     {  "pageFlow": "登入流程",  "pageTitle": "登入頁面",  "apiCalls": [    {      "endpoint": "POST /api/v1/auth/login",      "requestParams": { "email": "...", "password": "..." },      "expectedStatus": 200,      "expectedResponse": { "token": "...", "userId": "..." },      "actualStatus": 200,      "actualResponse": { "token": "...", "userId": "..." },      "timestamp": "2025-12-24T10:30:00Z"    }  ]}
     ```

### 第二階段：API 驗證與健康度檢測

1. **批次 API 測試**
   - 撰寫自動化腳本（Python、Bash/cURL 或其他語言）
   - 從第一階段的記錄檔案中讀取所有 API 呼叫資訊
   - 逐一執行這些 API，使用相同的請求參數和認證資訊
2. **結果比對與分析**
   - 比較預期響應與實際響應的以下維度：
     - **狀態碼**：是否與預期相符
     - **響應結構**：JSON 欄位是否齊全
     - **回應內容**：資料值是否符合邏輯（例如非空值、有效格式）
     - **回應時間**：是否超過定義的 SLA 閾值
   - 產生詳細的差異報告，標記異常項目
3. **健康度評分**
   - 計算以下指標：
     - API 成功率：成功呼叫 / 總呼叫數
     - 平均回應時間
     - 異常呼叫清單及其影響等級（Critical / Warning / Info）
4. **輸出報告**
   - 生成易讀的健康度檢測報告，包含：
     - 整體健康度評分（例如 95%）
     - 按端點分類的成功/失敗統計
     - 異常 API 詳細說明及建議修復方案
     - 時間序列分析（若執行多次檢測）

## 技術架構

```
[Claude Code]
    ↓
[Chrome 瀏覽器 + DevTools Network 監控]
    ↓
[API 呼叫映射表（JSON/CSV）]
    ↓
[自動化測試腳本（Python/Bash）]
    ↓
[健康度檢測結果 + 詳細報告]
```

## 預期優勢

- **自動化程度高**：無需手工撰寫 API 測試用例
- **真實性**：基於實際使用者介面互動，涵蓋實際業務流程
- **易於維護**：若頁面流程變更，僅需重新錄製
- **快速迭代**：可定期執行檢測，及時發現迴歸問題

## 注意事項

- 確保測試環境資料安全，避免在生產環境進行此操作
- 對於涉及認證的 API，妥善管理令牌和敏感資訊
- 定期更新預期結果，避免誤判
- **務必完整記錄 POST/PUT/PATCH 等方法的 Request Body**：
  - 第一階段錄製時，必須確保所有非 GET 方法的 API 都有完整記錄其請求本體（Request Body）
  - 若 Request Body 記錄不完整或為空，第二階段測試時將因參數缺失導致 API 回傳 400（Bad Request）或 403（Forbidden）等錯誤
  - 特別注意動態參數（如員工 ID、日期範圍等），需確認是否需要根據測試帳號調整
- **SLA 閾值設定應考量框架特性**：
  - 對於 ABP Framework 等專案，應用程式啟動後首次呼叫各 API 會因 JIT 編譯、依賴注入初始化等因素導致回應時間較長
  - 建議將 SLA 閾值設定為較寬鬆的數值（例如 10000ms），或區分首次呼叫與後續呼叫的閾值標準

## 測試策略

### 策略類型

本系統支援三種測試策略，以適應不同類型的 API：

| 策略值 | 說明 | 適用場景 | 驗證邏輯 |
|--------|------|----------|----------|
| `full_call` | 完整呼叫 | GET 查詢、POST 查詢（不修改資料） | 預期狀態碼 200 + 驗證回傳結構 |
| `liveness_probe` | 存活性探測 | POST/PUT/DELETE 修改類 API | 預期狀態碼 400/422，證明 API 存活 |
| `skip` | 跳過不測試 | 特殊情況（如需人工介入） | 不執行測試 |

### 使用時機

1. **full_call（預設）**
   - 所有查詢類 API
   - 不會產生副作用的 POST 請求（如搜尋、驗證）
   - 只關注回傳結構是否正確，不關注資料筆數或內容

2. **liveness_probe**
   - DELETE、PUT、PATCH 等會修改資料的 API
   - POST 新增資料的 API
   - 故意傳送不完整參數（如缺少必填欄位）
   - 預期 API 回傳 400（Bad Request）或 422（Unprocessable Entity）
   - 只要有回傳驗證錯誤，即證明 API 路由、Controller、中間件正常運作

3. **skip**
   - 需要特定前置條件的 API（如需先建立資料）
   - 有強制驗證機制無法繞過的 API
   - 測試資料單據不匹配的情況

### 記錄格式範例

```json
{
  "endpoint": "DELETE /api/app/users/DeleteUser",
  "fullUrl": "https://example.com/api/app/users/DeleteUser",
  "method": "DELETE",
  "testStrategy": "liveness_probe",
  "requestParams": {
    "Id": ""
  },
  "expectedStatus": 400,
  "actualStatus": 400,
  "actualResponse": {
    "note": "預期驗證錯誤，證明 API 存活"
  },
  "timestamp": "2025-12-29T10:00:00Z"
}
```

### 驗證邏輯

- **full_call**：實際狀態碼必須等於預期狀態碼（通常為 200）
- **liveness_probe**：實際狀態碼為 400 或 422 視為成功
- **skip**：不執行測試，不計入成功或失敗統計
