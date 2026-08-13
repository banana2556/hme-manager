<p align="center">
  <img src="static/logo.svg" width="96" alt="HME Manager logo">
</p>

<h1 align="center">HME Manager</h1>

<p align="center">零相依、自架的 iCloud「隱藏我的電子郵件」管理後台與 HTTP API。</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/deploy-Docker-2496ED.svg" alt="Docker">
</p>

## 功能

- 管理「隱藏我的電子郵件」信箱：建立、列出、停用、啟用、刪除與 CSV 匯出。
- **收件匣讀信**：用同一份 Session 直接讀 iCloud 網頁郵件（資料夾、清單、內容），自動偵測並一鍵複製驗證碼——用別名註冊服務後，驗證信不用離開工作台。
- **雙區域支援**：全球（icloud.com）與中國大陸（icloud.com.cn）帳號皆可匯入，區域依主機自動判定，Origin/Referer/langCode 一併處理。
- 固定格式的 HTTP API；所有 `/v1/*` 皆以 `X-API-Key` 驗證。
- Session 只透過 iCloud 網頁請求的 **Copy as cURL (bash)** 或 HAR 匯入，不接收 Apple ID、密碼或 2FA。
- **自動刷新**預設啟用，每 10 分鐘使用現有 Session 保活；失效時自動停用。
- 響應式工作台：**信箱清單**、**收件匣**、**API Builder**、**Session & 自動刷新**，支援亮／暗主題、手機版與 toast 操作回饋。
- 純 Python 標準庫、**零第三方相依**；多執行緒 HTTP 服務；支援本機、Docker 與 Render。

## 快速開始

### 1. 取得專案

```bash
git clone https://github.com/banana2556/hme-manager.git
cd hme-manager
```

### 2. 環境變數

| 變數 | 必填 | 說明 |
| --- | --- | --- |
| `HME_API_KEY` | ✅ | API 與後台共用的金鑰；未設定時拒絕所有請求 |
| `ICLOUD_HME_CONFIG` | | 匯入後的 Session 設定路徑；預設 `hme-config.json`，Docker 為 `/data/hme-config.json` |
| `HME_STATE_DIR` | | Session 檢查與自動刷新狀態目錄；預設 `state`，Docker 為 `/data/state` |

macOS / Linux：

```bash
export HME_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

Windows PowerShell：

```powershell
$env:HME_API_KEY = (python -c "import secrets; print(secrets.token_urlsafe(32))")
```

### 3. 啟動服務

#### 本地（Python 3.10+）

```bash
python web_app.py
```

開啟 <http://127.0.0.1:8000>，輸入剛才的 `HME_API_KEY`。

#### Docker

```bash
cp .env.example .env         # 將 HME_API_KEY 改成隨機金鑰
docker compose up -d --build
```

#### Render（一鍵）

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/banana2556/hme-manager)

### 4. 匯入 Session

1. 前往 [iCloud+](https://www.icloud.com/icloudplus/)（大陸帳號改用 [icloud.com.cn](https://www.icloud.com.cn/icloudplus/)），開啟 **Hide My Email（隱藏我的電子郵件）**。
2. 按 **F12** 開啟 DevTools → Network，找到包含 `list?clientBuildNumber` 的請求。
3. 對該請求選擇 **Copy as cURL (bash)**；也可匯出包含 request cookies 的 HAR。
4. 到後台的 **Session & 自動刷新** → **手動匯入 Session** 貼上並送出。區域（全球／中國大陸）依主機自動判定。
5. 若要在**收件匣**讀信，匯入前請先在 iCloud 網頁開啟過一次「郵件」，確保 cookie 帶有郵件授權（`X-APPLE-WEBAUTH-PCS-Mail`）。

## API

所有 `/v1/*` 需帶 `X-API-Key: <你的金鑰>`；`/health` 免驗證。

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/health` | 健康檢查 |
| GET | `/v1/session/status` | 目前 Session 狀態（含 `region`） |
| POST | `/v1/session/refresh` | 用現有 Session 做一次低風險檢查 |
| POST | `/v1/session/import` | 匯入 Session（body：`{"curl_text": "..."}`；支援 icloud.com / icloud.com.cn） |
| GET | `/v1/aliases` | 列出信箱 |
| POST | `/v1/aliases` | 建立信箱（body：`{"label": "...", "note": "..."}`） |
| POST | `/v1/aliases/{id}/disable` · `/enable` · `/delete` | 停用 / 啟用 / 刪除 |
| GET | `/v1/aliases/export.csv` | 匯出 CSV |
| GET | `/v1/mail/folders` | 郵件資料夾清單 |
| GET | `/v1/mail/messages?folder=&limit=&offset=&to=` | 郵件清單（`folder` 省略時自動用收件匣；`to` 可依收件地址過濾，例如單一 HME 別名） |
| GET | `/v1/mail/messages/{guid}` | 讀取單封郵件（text/html/附件中繼資料） |
| GET · POST | `/v1/auto-refresh` | 讀取或更新自動刷新設定 |
| POST | `/v1/auto-refresh/run` | 立即執行一次刷新 |

回應一律是固定信封：

```json
{ "ok": true, "data": {}, "error": null, "meta": { "service": "hme-manager", "version": "1", "requestId": null } }
```

## 收件匣讀信

「收件匣」分頁會用同一份 Session 讀取 iCloud 網頁郵件（JSON-RPC over `pNN-mailws.icloud.com`）。郵件服務的分區（`pNN`）與 HME 分區不一定相同，因此會先向 iCloud `setup` 服務查詢正確的郵件主機，查詢失敗才退回推導值。開啟一封郵件時會自動掃描主旨／內文，偵測到 4–8 位數的驗證碼即可一鍵複製；HTML 內文會放在 `sandbox` 的 iframe 中顯示，避免遠端內容存取工作台。

收件匣可依 **HME 別名** 過濾：用工具列的信箱下拉選單，或在「信箱清單」點某列的 **收件** 直接跳轉。過濾時會掃描該資料夾最近 300 封郵件的收件人欄位（Apple 私有 API 沒有伺服器端收件人搜尋），回應會帶 `matchedCount` / `scannedCount` / `scanComplete` 說明掃描範圍。

若收件匣回報 `SESSION_MISSING` 或郵件授權不足，請在 iCloud 網頁先開啟一次「郵件」再重新匯入 Session（cookie 需包含郵件授權）。

範例：

```bash
curl -X POST "http://127.0.0.1:8000/v1/aliases" \
  -H "X-API-Key: $HME_API_KEY" \
  -H "Content-Type: application/json" \
  --data '{"label":"GPT","note":"memo"}'
```

## 測試

```bash
python -m unittest discover -s tests -v
```

## 授權

[MIT](LICENSE) © [banana2556](https://github.com/banana2556) · [專案首頁](https://github.com/banana2556/hme-manager)
