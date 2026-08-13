---
target: static/index.html
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
timestamp: 2026-08-13T05-37-02Z
slug: static-index-html
---
Method: dual-agent (A: e804080b-e2ce-46f3-9551-967f5b03f37b · B: 8ca396ea-cbc2-40ed-9f29-5405dd3bc47d)

# Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | 系统状态可见性 | 3 | 「重新整理」与 Builder「送出」无进行中状态;邮件缓存状态只写进 sr-only 的 #status |
| 2 | 贴近真实世界 | 3 | 表头中英混排;「必要資料 metadata 是 / session 是」偏内部黑话 |
| 3 | 用户控制与自由 | 2 | showView 写 location.hash 却无 hashchange 监听,返回键静默失效;API Key 弹窗无 dialog 语义、无焦点陷阱 |
| 4 | 一致性与标准 | 3 | 视觉高度一致,但 ARIA 失准:endpointList 用 listbox 装 aria-pressed 按钮;aliasTabs 无 role="tab" |
| 5 | 错误预防 | 3 | 删除有 confirm、Builder 有占位符校验;保活间隔可手输 0/-50 无客户端拦截 |
| 6 | 识别而非回忆 | 3 | 端点模板+示例免记 API 形状;但 Builder 要求真实 anonymousId,别名表却不显示该列 |
| 7 | 灵活与高效 | 2 | 零快捷键、无批量操作;本地过滤与缓存是仅有的提速手段 |
| 8 | 美学与极简 | 3 | 令牌纪律好;forwardTo 整列重复、.method-badge 死元素 |
| 9 | 错误恢复 | 3 | SESSION_MISSING 有明确恢复路径;导入失败详因只活在 3.2 秒 toast;网络故障误报「API Key 無效」 |
| 10 | 帮助与文档 | 3 | 四步导入教学在刀口上;无站内文档入口 |
| **Total** | | **28/40** | **Good(弱项集中在控制自由与效率)** |

# Design Specificity Verdict

**LLM 评估**:为产品而写,不是换皮后台。验证码药丸把「验证码是心跳」做成签名组件;四步导入教学、session 圆点+倒计时、别名行「收件」直达都只属于这个 HME 工作台。外壳是标准 admin 骨架,但在 Operate 模式下是正确的克制;产品性格在细节里,与 DESIGN.md「调度室」承诺逐条兑现。

**确定性扫描**:index.html+app.js 零发现;app.css 有 5 条 advisory 级 design-system 漂移——radius 12px(.sidebar-foot:176)、8px(.tab-button:319)、7px(.copy-btn:363)、11px(.toast:561)不在 DESIGN.md 刻度,17px(.mail-head-subject:448)不在字级坡道。其中 8px/7px 是嵌套同心几何、设计上可辩护(假阳性倾向);12px/11px/17px 为真实漂移,应统一或入册。A 认为「CSS 逐条兑现设计文档」,检测器抓到了 A 漏掉的 5 处 token 漂移——这正是双评估的价值。

**可视化覆盖**:本会话无浏览器自动化工具,浏览器注入与截图步骤跳过;fallback 信号为 CLI detector only。

# Overall Impression

一个真的为自己产品写的工作台:纪律、安全、恢复文案都在线。最大的机会不在视觉——在**核心闭环的最后一公里**:等验证码这个最高频、最焦虑的时刻,系统把工作全部推给用户的手指(狂点重新整理,还会被清掉阅读状态)。

# What's Working

1. **验证码药丸是产品原则的可视化身**:四个草堆扫描、命中即在第一眼位置渲染、一击入剪贴板并确认。
2. **恢复路径写进了空态与错误文案**:SESSION_MISSING → 指路导入;占位符校验直接教怎么改;失败时刻教用户走自己的仪式。
3. **设计纪律与工程诚实互相兑现**:阴影只给悬浮层、单 accent、escapeHtml 全覆盖、邮件 HTML 只进 sandbox iframe、三层缓存支撑即时过滤。

# Priority Issues

1. **[P1] 等验证码的空窗期无系统支持**:收件匣不轮询,「重新整理」全量重抓并轰掉阅读窗与选中态。修法:收件匣可见期间轻量轮询当前资料夹,增量合并到顶部,保留 currentMailGuid 与详情缓存。(命令:$impeccable harden / polish)
2. **[P1] Builder 示例响应与真实响应无法区分**:选中端点即填一份逼真假成功 JSON,example/actual 无任何视觉区分,用户可能相信 delete 已执行。修法:「回應範例」标签 + 视觉降权,送出后切「實際回應」。(命令:$impeccable clarify)
3. **[P1] 服务器不可达被误诊为「API Key 無效」**:verifyApiKey 把 fetch 失败当 401,boot 弹窗质问、提交报无效,可能诱导覆盖正确 key。修法:区分网络错误与 401,显示「無法連線到伺服器」。(命令:$impeccable harden)
4. **[P2] 半实现的 hash 路由让返回键失灵**:写 hash 不听 hashchange。修法:补 hashchange 监听驱动 showView。(命令:$impeccable harden)
5. **[P2] 导入失败的具体错误 3.2 秒后蒸发**:高风险仪式的失败诊断只在 toast 闪现,#importResult 永远是通用句。修法:把完整 error envelope 写进 #importResult。(命令:$impeccable clarify)

# Persona Red Flags

**Alex(重度用户)**:全站零快捷键(/ 聚焦、Ctrl+Enter 送出、j/k 走信、Esc 关表单全缺);等验证码只能狂点且每点丢一次上下文;Builder disable 一个别名要 6 次上下文切换(表格不给 anonymousId 也不给直达);160+ 别名下拉无搜索;送出钮不禁用可双击建两个别名。

**Sam(屏幕阅读器)**:焦点湮灭系统性存在(整表/整列 innerHTML 重建后焦点跌回 body);#mailReader 无 aria-live,验证码药丸对 SR 静默;API Key 弹窗无 role="dialog"/焦点陷阱;endpointList/aliasTabs ARIA 结构错;未读只有视觉双讯号无文本等价;建立表单用 placeholder 当 label。正面:focus-visible 全局环、图标钮有 aria-label、toasts aria-live。

**Riley(压力测试)**:验证码正则无词边界("Shipping 12345678" 命中 pin;任意 6 位数成药丸);保活间隔可存 0/-50;导入成功悄悄改掉 Builder 选中端点与输出区;401 解锁后 init() 清掉手编 JSON;侧栏「自動刷新 載入中」失败时永远说谎;分页重叠时「載入更早」按钮消失;非 JSON 响应时 SyntaxError 原文进 toast。正面:XSS 防护完整、导入失败保留输入、load-more 禁用态完整。

# Minor Observations

- .method-badge 死元素;setStatus 第二参数被静默丢弃;邮件缓存 caption 应可见化;建立成功连发两条重复 toast;forwardTo 整列重复真实邮箱;标题层级 h1→h3 跳档;th 无 scope;toast 上限静默挤掉最旧;「刷新」vs「重新整理」双词并存;阅读器 iframe 固定 min-height 短信留白。
- 检测器 5 条 CSS 漂移:12px/11px 圆角与 17px 字级应统一或入册;8px/7px 为同心几何应在 DESIGN.md 记嵌套规则。

# Questions to Consider

1. 建立别名成功的那一刻,下一步 100% 是"去注册然后等验证码"——如果「建立」直接把收件匣带入"等待此别名第一封信"的轮询态,闭环还剩几次点击?
2. API Builder 是"活文档"还是"操作工具"?是文档,示例就该长得像文档;是工具,{anonymousId} 就该能从缓存里挑。
3. 验证码检测失败时 UI 选择沉默——「未偵測到驗證碼?複製郵件摘要」的降级出口是否更像调度室?
