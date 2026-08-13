# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

單一使用者：專案作者本人，自架自用（伺服器跑在自己的機器或私有部署上）。不設多使用者、多租戶或權限分級。

情境：註冊第三方服務時使用 iCloud「隱藏我的電子郵件」（HME）別名保護真實信箱；註冊後需要立刻取得寄到該別名的驗證碼；平時以桌面瀏覽器操作（主要在 Windows [推斷：依開發環境]），也會用自己的腳本透過 HTTP API 自動化操作。

倉庫公開且提供 Deploy-to-Render，但那是順帶的開源副產品，不是設計對象；產品決策以單一操作者為準。

## Product Purpose

自架的 HME 管理後台與 HTTP API：管理別名（建立、停用、啟用、刪除、匯出）、讀取別名收件（資料夾、清單、內文）、自動偵測驗證碼一鍵複製、以低風險請求保活 session。

成功的樣子：從「用別名註冊一個服務」到「驗證碼進剪貼簿」在幾秒內完成，全程不用開 icloud.com，真實信箱不出現在任何第三方面前。

## Positioning

不碰 Apple ID 憑證的 HME 工具：只接收使用者自己從瀏覽器複製出來的已登入 session（cURL/HAR 導入），從不經手帳號、密碼或 2FA。同一個自架服務同時餵 UI 和腳本——固定的 `/v1` JSON 信封讓自動化與工作台看到完全一致的世界。支援全球（icloud.com）與中國大陸（icloud.com.cn）分區。

## Operating Context

- Session 取得儀式：在 iCloud 網頁開啟「郵件」與 Hide My Email，DevTools → Network → 對 `/v2/hme/list` 請求 Copy as cURL（或匯出 HAR），貼進後台導入。cookie 會過期（PCS-Mail 授權更快），過期就重複此儀式。
- 自動刷新每 10 分鐘用 `/v2/hme/list` 保活；401/403/421 視為授權失效，自動停用並要求重新導入。
- 上游是 Apple 私有 API（`pNN-maildomainws` 的 HME 端點、`pNN-mailws` 的 JSON-RPC 與 raw RFC822 通道、setup 服務的主機解析），無文件、會漂移；郵件分區與 HME 分區不一定相同。
- 部署：本機 `python web_app.py`、Docker、Render 三選一；所有 `/v1/*` 以 `HME_API_KEY`（X-API-Key）保護。
- 郵件內文在 sandbox iframe 中渲染，遠端內容不得觸及工作台本身。

## Capabilities and Constraints

能力（現況）：別名 CRUD 與 CSV 匯出；收件匣讀信（資料夾、清單、內文、附件中繼資料）；依別名過濾收件（前端快取本地過濾 + API `to=` 參數）；4–8 位驗證碼偵測與一鍵複製；session 導入/狀態/刷新；自動刷新設定與立即執行；API Builder（請求預覽、curl、實際送出）；亮暗主題；繁體中文介面。

硬約束（使用者確認，未來工作必須保留）：

- **絕不接收 Apple ID 密碼或 2FA**。唯一的認證輸入是使用者自己導入的 web session；任何需要帳密的功能都在範圍外。
- **API 信封與既有路由不可破壞**：`{ok, data, error, meta}` 信封與 `/v1/*` 語義有外部消費者（使用者自己的腳本）。可以加欄位、加端點；不可改既有欄位語義或移除端點。

其他必須尊重的產品事實：

- Session cookie 是最高機密：不進 git（`hme-config.json`、`state/` 已 gitignore）、不寫進日誌與錯誤訊息。
- 郵件功能是唯讀的；不提供寄信、刪信、標記。
- Apple 端不可控：解析要容錯（欄位拼寫漂移、payload 形狀變化），session 失效要誠實回報（`SESSION_MISSING` / `SESSION_EXPIRED`）並指出重新導入的路徑。

慣例（非硬約束，使用者明示可因充分理由調整）：

- 零第三方相依（純 Python 標準庫 + 原生 JS/CSS）。
- 介面語言為繁體中文。

## Brand Commitments

名稱 **HME Manager**；GitHub `banana2556/hme-manager`；MIT 授權；logo 在 `static/logo.svg`。文案語氣：務實、精確、短句、繁體中文。無其他具約束力的視覺承諾。

## Evidence on Hand

- 作者自己的營運實例：真實 session、160+ 個實際使用中的別名（開發與驗證都對真實 Apple API 進行）。
- `README.md`：功能、部署、API 文件與收件匣說明。
- `tests/`：106 項單元測試（協定解析、路由、session 管理、前端資產約束）。
- 沒有使用者見證、案例研究、使用統計——未來任何面向外部的敘述都不得虛構這些。

## Product Principles

1. **Session 進，憑證免。** 信任邊界是使用者自己導入的 cookie；需要 Apple 帳密的功能不做。
2. **驗證碼是心跳。** 「別名 → 註冊 → 驗證碼進剪貼簿」的秒級閉環是第一優先的工作流；其他功能不得讓這條路變慢。
3. **UI 與腳本吃同一條 API。** `/v1` 信封是契約：寧可加欄位，不改語義；工作台能做的，curl 一定也能做。
4. **預期 Apple 漂移。** 私有端點會變：解析容錯、狀態誠實、失敗時給出明確的恢復步驟（重新導入），絕不假裝 session 還活著。
5. **單人尺度。** 為一位操作者的速度最佳化（快取、一鍵複製、即時本地過濾）；不做多租戶、協作或權限功能。
