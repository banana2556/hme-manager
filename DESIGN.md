---
name: HME Manager
description: 零相依、自架的 iCloud「隱藏我的電子郵件」調度工作台
colors:
  console-fog: "#f4f5f7"
  panel-white: "#ffffff"
  recessed-gray: "#f6f7f9"
  console-ink: "#17181c"
  dimmed-signal: "#5c6674"
  hairline: "#e4e7ec"
  soft-hairline: "#eef0f4"
  dispatch-blue: "#0669dd"
  deep-dispatch: "#0353b8"
  dispatch-text: "#0353b8"
  dispatch-tint: "rgba(6, 105, 221, 0.10)"
  signal-green: "#189e6a"
  caution-amber: "#a06a13"
  alert-red: "#cf3340"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', 'Noto Sans TC', 'Microsoft JhengHei', system-ui, sans-serif"
    fontSize: "15.5px"
    fontWeight: 700
    letterSpacing: "-0.01em"
  heading:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', 'Noto Sans TC', 'Microsoft JhengHei', system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 700
    letterSpacing: "-0.01em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', 'Noto Sans TC', 'Microsoft JhengHei', system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', 'Noto Sans TC', 'Microsoft JhengHei', system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    letterSpacing: "0.05em"
  mono:
    fontFamily: "ui-monospace, 'SF Mono', 'Cascadia Code', Consolas, 'Courier New', monospace"
    fontSize: "12.5px"
    fontWeight: 400
rounded:
  control: "9px"
  nav: "10px"
  card: "14px"
  modal: "16px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "14px"
  md: "18px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.dispatch-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "34px"
  button-primary-hover:
    backgroundColor: "{colors.deep-dispatch}"
    textColor: "#ffffff"
  button-secondary:
    backgroundColor: "{colors.panel-white}"
    textColor: "{colors.console-ink}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "34px"
  button-secondary-hover:
    backgroundColor: "{colors.recessed-gray}"
    textColor: "{colors.console-ink}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.alert-red}"
    rounded: "{rounded.control}"
    padding: "0 13px"
    height: "34px"
  input:
    backgroundColor: "{colors.panel-white}"
    textColor: "{colors.console-ink}"
    rounded: "{rounded.control}"
    padding: "6px 11px"
    height: "34px"
  card:
    backgroundColor: "{colors.panel-white}"
    rounded: "{rounded.card}"
    padding: "18px"
  nav-item-active:
    backgroundColor: "{colors.dispatch-tint}"
    textColor: "{colors.dispatch-text}"
    rounded: "{rounded.nav}"
    height: "38px"
  code-chip:
    backgroundColor: "{colors.dispatch-tint}"
    textColor: "{colors.dispatch-text}"
    rounded: "{rounded.pill}"
    padding: "0 15px"
    height: "36px"
---

# Design System: HME Manager

## Overview

**Creative North Star: "調度室（The Dispatch Desk）"**

這是一間單人機房的操作台：安靜、精確、一切一眼可讀。介面不表演，只調度——別名、session、驗證碼在幾秒內各就各位。每個表面都假設操作者熟門熟路，因此資訊密度偏工具而非行銷，層級靠 hairline 與留白而非裝飾建立，唯一的藍色只在「現在該看這裡」的地方出現。

視覺哲學：精確而克制（refined and restrained）。控件手感像儀表開關——邊界清晰、回饋即時、不位移不彈跳。亮暗雙主題服務不同機房照明，語義不變：同一顆 token 在兩個主題下扮演同一個角色。已確認的反面參照：不做行銷式漸層與玻璃裝飾，不做卡片堆卡片的儀表板拼貼。

**Key Characteristics:**

- 平面 hairline 層級：邊框定義面板，陰影只屬於懸浮層
- 單一 accent（調度藍），狀態色只講狀態（綠/琥珀/紅）
- 圓點是狀態語言：session 指示、未讀、toast 一律小圓點
- mono 只給資料：地址、代碼、時間戳
- 繁體中文短句文案，控件直接說出動作

## Colors

一個工作用的中性灰階，加一支調度藍與三支狀態色；accent 稀有性就是它的意義。

### Primary

- **調度藍 Dispatch Blue** (#0669dd)：主按鈕底色、聚焦環、未讀圓點、選中底色的來源。只用於「當前動作」與「當前位置」。
- **深調度 Deep Dispatch** (#0353b8)：主按鈕 hover。
- **調度文字 Dispatch Text** (#0353b8)：所有 accent 色「文字」一律用它（淺色主題下與 Deep Dispatch 同值；暗色主題為 #82bbff）——保證 ≥4.5:1。
- **調度染 Dispatch Tint** (rgba(6,105,221,0.10))：導航激活、列表選中、驗證碼藥丸的底。

### Neutral

- **調度台霧灰 Console Fog** (#f4f5f7)：頁面背景。
- **面板白 Panel White** (#ffffff)：卡片、表格、清單的表面。
- **凹面灰 Recessed Gray** (#f6f7f9)：hover 底、分段控件槽、代碼塊底。
- **墨黑 Console Ink** (#17181c)：正文與標題。
- **弱訊灰藍 Dimmed Signal** (#5c6674)：次要文字、placeholder、meta；在任何底上維持 ≥4.5:1。
- **髮絲線 Hairline** (#e4e7ec) 與 **軟髮絲 Soft Hairline** (#eef0f4)：面板邊界與列表分隔。

### Semantic

- **通行綠 Signal Green** (#189e6a)：session 可用、啟用中、成功 toast。
- **警示琥珀 Caution Amber** (#a06a13)：未確認、待檢查。
- **告警紅 Alert Red** (#cf3340)：失效、刪除、錯誤。

暗色主題在 `static/app.css` 的 `[data-theme="dark"]` 與 `prefers-color-scheme` 回退中定義同名角色（詳值見 `.impeccable/design.json` 的 colorMeta）；語義與淺色一一對應。

### Named Rules

**The One-Accent Rule.** 全站只有調度藍一支 accent；它出現在 ≤10% 的畫面上。想強調，先用字重與層級，別加顏色。

**The Accent-Text Rule.** accent 色的「文字」永遠走 `--accent-text`；`--accent` 本體只給表面、環與圓點。這條規則就是對比度的保險絲。

**The Status-Is-Status Rule.** 綠/琥珀/紅只講狀態，不做裝飾；反之狀態永遠帶顏色以外的第二訊號（文字或圓點位置）。

## Typography

**Body Font:** 系統 UI 棧（-apple-system / SF Pro Text / Segoe UI / Noto Sans TC / Microsoft JhengHei）
**Label/Mono Font:** ui-monospace（SF Mono / Cascadia Code / Consolas）

**Character:** 系統字的中性聲音，靠字重（400/500/600/700）與 11–15.5px 的窄幅級距說話；不引入展示字體——調度室不需要招牌。

### Hierarchy

- **Title** (700, 15.5px, letter-spacing -0.01em)：頂欄視圖標題。
- **Heading** (700, 13.5px)：卡片標題（h3）。
- **Body** (400, 14px, line-height 1.5)：正文與控件文字（控件 13px）。
- **Label** (700, 11px, letter-spacing 0.05em, uppercase)：表頭與欄位標籤。
- **Mono** (400, 12–12.5px)：信箱地址、代碼、curl、時間戳。

### Named Rules

**The Mono-Is-Data Rule.** mono 只用於資料本身（地址、guid、代碼、JSON），絕不當「科技感」裝飾。

## Layout

240px 固定側欄 + 流動工作區（內容上限 1440px 置中）。頂欄 58px，sticky，半透明毛玻璃（backdrop-filter blur 10px）——這是全站唯一的玻璃，功能是滾動時保持定位可讀。工作區內距 20/24px；區塊間距 14–18px；控件間隙 8px。

雙欄工作面（收件匣 minmax(290px,380px)+1fr、API Builder minmax(290px,370px)+1fr）在 960px 斷點收成單欄；側欄同時收成頂部圖標列（文字隱藏、圖標 42px 觸控高度）。表格設 min-width 780px，窄屏橫向滾動而不擠壓欄位。

## Elevation & Depth

平面系統：面板靠 1px hairline 邊框與底色差建立層級，靜止的表面沒有陰影。陰影只屬於真正懸浮的東西。

### Shadow Vocabulary

- **懸浮層** (`box-shadow: 0 12px 32px rgba(16,24,40,0.16)`，暗色 `0 16px 40px rgba(0,0,0,0.55)`)：toast 與 API Key 彈窗。
- **分段滑塊** (`box-shadow: 0 1px 2px rgba(16,24,40,0.10)`)：result-tabs 的選中頁籤。

### Named Rules

**The One-Elevation Rule.** 每個表面只宣告一種層級手段：面板用邊框、懸浮層用陰影。1px 邊框疊寬陰影的「幽靈卡」不存在於這個系統。

## Shapes

圓角矩形一族：控件 9px、導航膠囊 10px、面板 14px、彈窗 16px、藥丸與徽章 999px。邊框一律 1px hairline；選中/聚焦靠 2px accent 外環（offset 2px），不改變形狀。小圓點（6–8px）是貫穿全站的狀態符號：session 指示、未讀標記、badge 前綴、toast 開頭。

## Components

### Buttons

- **Shape:** 圓角 9px，高 34px（移動端 40px+），padding 0 13px
- **Primary:** 調度藍底白字（600）；hover 深調度；active 維持深色——不位移
- **Secondary（預設）:** 面板白底 + hairline 邊框；hover 凹面灰底
- **Danger:** 透明底告警紅字；hover 紅染底——破壞性動作永遠是幽靈態，避免畫面常駐紅色
- **Icon button:** 34×34（移動端 40×40），透明底，hover 凹面灰
- **Focus:** 一律 2px 調度藍外環 offset 2px

### Inputs / Fields

- **Style:** 面板白底、hairline 邊框、9px 圓角、高 34px；placeholder 用弱訊灰藍（不再降透明度）
- **Focus:** 邊框轉調度藍 + 3px 調度染外暈
- **Textarea:** mono 12px，供 curl/HAR 貼上

### Navigation

- 側欄膠囊 38px 高、10px 圓角；預設弱訊灰藍、hover 凹面灰底墨黑字、激活調度染底 + 調度文字（600）
- 960px 以下收成頂部圖標列（42px），文字隱藏、title/aria-label 保留

### Cards / Containers

- **Corner:** 14px；**Background:** 面板白；**Border:** 1px hairline；**Shadow:** 無（見 One-Elevation）
- **Internal Padding:** 18px

### Table

- 表頭 sticky：11px uppercase label 灰字、面板白底、底邊 hairline
- 行分隔 soft hairline、hover 凹面灰；地址欄 mono + 行內複製鈕（26px ghost）

### Badges & Dots

- 徽章：999px 藥丸、11px/600、前綴 6px currentColor 圓點;on=通行綠染、off=灰染
- 獨立狀態點：7px（session）、8px（未讀/toast）

### Mail List Item

- 基準 400 字重；未讀：from/subject 轉 700 + 8px 調度藍圓點前綴
- 選中：調度染底，無位移無色條；日期 11px tabular-nums

### Toast

- 面板白底 + hairline 邊框 + 懸浮陰影;開頭 8px 狀態圓點（藍/綠/琥珀/紅）
- 進場 0.18s ease-out 上滑淡入，離場 0.22s 反向——全站唯一的授權動效

### 驗證碼藥丸（Signature Component）

收件匣偵測到 4–8 位驗證碼時出現的一鍵複製藥丸：999px、調度染底、調度藍 1px 邊框、調度文字 600，代碼本體 15.5px tabular-nums 加寬字距；hover 反轉為調度藍底白字。它是「驗證碼是心跳」原則的視覺化身，永遠出現在郵件標頭第一眼的位置。

## Do's and Don'ts

### Do:

- **Do** 面板一律 1px hairline 邊框、無陰影；陰影只給 toast、彈窗、分段滑塊。
- **Do** accent 文字一律 `--accent-text`（≥4.5:1）；accent 面積 ≤10%。
- **Do** 狀態用「顏色 + 圓點/文字」雙訊號；未讀用字重 700 + 圓點。
- **Do** 聚焦一律 2px 調度藍外環 offset 2px；鍵盤路徑與滑鼠等權。
- **Do** 觸控目標移動端 ≥34px（主要控件 40px+）；表格窄屏橫向滾動。
- **Do** 郵件 HTML 內文只在 sandbox iframe（白底）中渲染。

### Don't:

- **Don't** 彩色 border-left/right 色條（>1px）——狀態走圓點，選中走底色。
- **Don't** 漸層文字、裝飾性玻璃/模糊（毛玻璃只屬於頂欄的定位功能）。
- **Don't** 引入第二支 accent 色相或展示字體。
- **Don't** hover/active 位移或彈跳；回饋只用底色與邊框。
- **Don't** mono 當裝飾；非資料文字一律系統字。
- **Don't** 在面板上疊「邊框+陰影」雙層級（幽靈卡）。
