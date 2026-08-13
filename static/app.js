"use strict";

const API_KEY_PLACEHOLDER = "<API_KEY>";
const STORAGE_KEY = "hme-api-key";

const $ = (id) => document.getElementById(id);
const statusEl = $("status");
const viewTitleEl = $("viewTitle");
const responsePreviewEl = $("responsePreview");
const actualOutputEl = $("actualOutput");
const requestPreviewEl = $("requestPreview");
const curlOutputEl = $("curlOutput");
const methodBadge = $("methodBadge");
const endpointList = $("endpointList");
const tableEl = $("table");
const aliasSourceEl = $("aliasSource");
const aliasFilterInput = $("aliasFilterInput");
const aliasTabs = $("aliasTabs");
const aliasCountSub = $("aliasCountSub");
const createAliasForm = $("createAliasForm");
const sessionIndicatorEl = $("sessionIndicator");
const sessionMiniStatusEl = $("sessionMiniStatus");
const sessionMiniEl = $("sessionMini");
const sessionDotEl = $("sessionDot");
const autoRefreshMiniEl = $("autoRefreshMini");
const sessionMailEl = $("sessionMail");
const sessionRequiredEl = $("sessionRequired");
const sessionDsidEl = $("sessionDsid");
const sessionHostEl = $("sessionHost");
const sessionSavedAtEl = $("sessionSavedAt");
const sessionSyncedAtEl = $("sessionSyncedAt");
const sessionStateEl = $("sessionState");
const autoRefreshEnabledEl = $("autoRefreshEnabled");
const autoRefreshIntervalEl = $("autoRefreshInterval");
const autoRefreshStatusEl = $("autoRefreshStatus");
const sessionRegionEl = $("sessionRegion");
const mailFolderSelect = $("mailFolderSelect");
const mailAliasSelect = $("mailAliasSelect");
const mailListEl = $("mailList");
const mailReaderEl = $("mailReader");
const toastsEl = $("toasts");

const VIEW_TITLES = { aliases: "信箱清單", inbox: "收件匣", builder: "API Builder", session: "Session & 自動刷新" };

let aliasRows = [];
let aliasesLoadedOnce = false;
let lastSessionStatus = null;
let lastAliasSyncAt = null;
let lastSessionRefreshAt = null;
let lastAutoRefresh = null;
let autoRefreshCountdownTimer = null;
let currentOperation = "list";
let currentView = "aliases";
let mailFolders = [];
let mailMessages = [];        // currently displayed (after alias filter)
let mailAllMessages = [];     // cached messages of the current folder
let mailCacheFolder = null;
let mailCacheAt = null;
let mailTotal = null;
const mailDetailCache = new Map();
let mailAliasFilter = "";
let currentMailGuid = null;
let inboxLoadedOnce = false;

const operations = {
  status: { method: "GET", path: "/v1/session/status", body: null },
  refresh: { method: "POST", path: "/v1/session/refresh", body: null },
  list: { method: "GET", path: "/v1/aliases", body: null },
  create: { method: "POST", path: "/v1/aliases", body: { label: "GPT", note: "" } },
  disable: { method: "POST", path: "/v1/aliases/{anonymousId}/disable", body: null },
  enable: { method: "POST", path: "/v1/aliases/{anonymousId}/enable", body: null },
  delete: { method: "POST", path: "/v1/aliases/{anonymousId}/delete", body: null },
  mailFolders: { method: "GET", path: "/v1/mail/folders", body: null },
  mailMessages: { method: "GET", path: "/v1/mail/messages?limit=20&offset=0", body: null },
  mailMessage: { method: "GET", path: "/v1/mail/messages/{guid}", body: null }
};

const META = { service: "hme-manager", version: "1", requestId: null };
const responseExamples = {
  status: { ok: true, data: { metadataDetected: true, persistedSession: true, sessionValid: true, needsReauth: false, lastRefreshAt: 1778246060, lastValidAt: 1778246060, lastSavedAt: 1778246000, expiresHint: "apple-controlled", lastError: null, metadata: { dsid: "608658063", host: "p119-maildomainws.icloud.com" }, hme: { selectedForwardTo: "user@example.com", aliasCount: 1 } }, error: null, meta: META },
  refresh: { ok: true, data: { metadataDetected: true, persistedSession: true, sessionValid: true, needsReauth: false, lastRefreshAt: 1778246060, lastValidAt: 1778246060, lastSavedAt: 1778246000, expiresHint: "apple-controlled", lastError: null, metadata: { dsid: "608658063", host: "p119-maildomainws.icloud.com" }, hme: { selectedForwardTo: "user@example.com", aliasCount: 1 } }, error: null, meta: META },
  list: { ok: true, data: [{ origin: "ON_DEMAND", anonymousId: "example123", domain: "", forwardToEmail: "user@example.com", hme: "example.alias@icloud.com", label: "GPT", note: "", createTimestamp: 1778246060430, isActive: true, recipientMailId: "" }], error: null, meta: META },
  create: { ok: true, data: { origin: "ON_DEMAND", anonymousId: "newalias123", domain: "", hme: "new.alias@icloud.com", label: "GPT", note: "", createTimestamp: 1778246060430, isActive: true, recipientMailId: "" }, error: null, meta: META },
  disable: { ok: true, data: { anonymousId: "example123", isActive: false }, error: null, meta: META },
  enable: { ok: true, data: { anonymousId: "example123", isActive: true }, error: null, meta: META },
  delete: { ok: true, data: { anonymousId: "example123", deleted: true }, error: null, meta: META },
  mailFolders: { ok: true, data: [{ guid: "folder-guid-1", name: "Inbox", role: "INBOX", unreadCount: 2, totalCount: 48 }], error: null, meta: META },
  mailMessages: { ok: true, data: { folder: "folder-guid-1", offset: 0, total: 48, messages: [{ guid: "message-guid-1", from: "OpenAI <noreply@openai.com>", to: "example.alias@icloud.com", subject: "Your verification code", date: "2026-08-13T02:00:00+00:00", snippet: "Your code is 123456", isRead: false }] }, error: null, meta: META },
  mailMessage: { ok: true, data: { guid: "message-guid-1", from: "OpenAI <noreply@openai.com>", to: "example.alias@icloud.com", subject: "Your verification code", date: "2026-08-13T02:00:00+00:00", snippet: "", isRead: true, textBody: "Your code is 123456", htmlBody: "", attachments: [] }, error: null, meta: META }
};

// ---------- API key ----------
function getStoredApiKey() { return localStorage.getItem(STORAGE_KEY) || ""; }
function setStoredApiKey(key) { localStorage.setItem(STORAGE_KEY, key); }
function readApiKey() { return getStoredApiKey(); }

function apiHeaders() {
  const key = readApiKey();
  if (!key) { showModal(); throw new Error("MISSING_API_KEY"); }
  return { "Content-Type": "application/json", "X-API-Key": key };
}

// ---------- status / output ----------
function setStatus(text) {
  statusEl.textContent = text;
}

// ---------- toasts & clipboard ----------
function toast(message, kind = "info") {
  setStatus(message);
  if (!toastsEl) return;
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  toastsEl.appendChild(item);
  while (toastsEl.children.length > 4) toastsEl.removeChild(toastsEl.firstChild);
  window.setTimeout(() => {
    item.classList.add("leaving");
    window.setTimeout(() => item.remove(), 240);
  }, 3200);
}

async function copyText(text, label = "已複製") {
  if (!text) return false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const scratch = document.createElement("textarea");
      scratch.value = text;
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      scratch.remove();
    }
    toast(`${label}：${text.length > 42 ? text.slice(0, 42) + "…" : text}`, "ok");
    return true;
  } catch (error) {
    toast("複製失敗，請手動選取", "bad");
    return false;
  }
}

function show(data, isError = false) {
  setStatus(isError ? "發生錯誤" : "完成", isError);
  if (isError) {
    const message = data && data.error && (data.error.message || data.error.code)
      ? (data.error.message || data.error.code)
      : "發生錯誤";
    toast(String(message).slice(0, 160), "bad");
  }
  showActualOutput(data);
}
function showActualOutput(data) {
  actualOutputEl.textContent = JSON.stringify(data, null, 2);
  responsePreviewEl.hidden = true;
  actualOutputEl.hidden = false;
}
function showResponseExample() {
  responsePreviewEl.hidden = false;
  actualOutputEl.hidden = true;
}

async function request(path, options = {}) {
  try {
    const response = await fetch(path, options);
    if (response.status === 401) { showModal(); return null; }
    const data = await response.json();
    if (!response.ok || data.ok === false) { show(data, true); return null; }
    show(data);
    return data;
  } catch (error) {
    show({ ok: false, error: String(error) }, true);
    return null;
  }
}

// ---------- view switching ----------
function showView(name) {
  currentView = VIEW_TITLES[name] ? name : "aliases";
  document.querySelectorAll(".view").forEach((view) => {
    view.hidden = view.id !== `view-${currentView}`;
  });
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === currentView);
  });
  viewTitleEl.textContent = VIEW_TITLES[currentView];
  if (aliasCountSub) aliasCountSub.hidden = currentView !== "aliases";
  window.location.hash = currentView;
  if (currentView === "aliases") { renderAliases(); refreshAliasTable(); }
  if (currentView === "session") { loadStatus(); loadAutoRefresh(); }
  if (currentView === "inbox" && !inboxLoadedOnce) { inboxLoadedOnce = true; initInbox(); }
}

// ---------- session info ----------
function formatSessionTime(value) {
  if (!value) return "未知";
  const date = value instanceof Date ? value : new Date(Number(value) * 1000);
  return Number.isNaN(date.getTime()) ? "未知" : date.toLocaleString();
}
function yesNo(value) { return value ? "是" : "否"; }

function inferForwardTo(status) {
  if (status && status.hme && status.hme.selectedForwardTo) return status.hme.selectedForwardTo;
  const firstAlias = aliasRows.find((alias) => alias.forwardToEmail);
  return firstAlias ? firstAlias.forwardToEmail : "未知";
}

function regionLabel(status) {
  const region = status && status.region
    ? status.region
    : (status && status.metadata && status.metadata.host && status.metadata.host.endsWith(".icloud.com.cn") ? "china" : null);
  if (region === "china") return "中國大陸（icloud.com.cn）";
  if (region === "global") return "全球（icloud.com）";
  return status && status.metadata && status.metadata.host ? "全球（icloud.com）" : "未知";
}

function renderSessionInfo(status = lastSessionStatus) {
  lastSessionStatus = status || lastSessionStatus || {};
  const s = lastSessionStatus;
  const metadata = s.metadata || {};
  const hme = s.hme || {};
  const hasMetadata = Boolean(s.metadataDetected || metadata.dsid);
  const hasSession = Boolean(s.persistedSession || s.sessionValid);
  const hasApiKey = Boolean(readApiKey());
  const requiredOk = hasMetadata && hasSession && hasApiKey;
  const aliasCount = aliasRows.length || hme.aliasCount || 0;
  if (sessionMailEl) {
    sessionMailEl.textContent = inferForwardTo(s);
    sessionRequiredEl.textContent = `metadata ${yesNo(hasMetadata)} / session ${yesNo(hasSession)} / API key ${yesNo(hasApiKey)}`;
    sessionDsidEl.textContent = metadata.dsid || "未知";
    sessionHostEl.textContent = metadata.host || "未知";
    if (sessionRegionEl) sessionRegionEl.textContent = regionLabel(s);
    sessionSavedAtEl.textContent = formatSessionTime(s.lastSavedAt || s.configUpdatedAt);
    sessionSyncedAtEl.textContent = lastAliasSyncAt ? `${formatSessionTime(lastAliasSyncAt)} / ${aliasCount} 筆` : `尚未同步 / ${aliasCount} 筆`;
  }
  let stateText;
  let stateKind;
  if (s.needsReauth) {
    stateText = `需要重新匯入 Session${s.lastError ? "：" + s.lastError : ""}`;
    stateKind = "bad";
  } else if (s.sessionValid) {
    const checkedAt = s.lastValidAt || s.lastRefreshAt || lastSessionRefreshAt;
    stateText = checkedAt ? `可用，最近刷新 ${formatSessionTime(checkedAt)}` : "可用";
    stateKind = "ok";
  } else if (requiredOk) {
    stateText = `已保存，尚未確認可用${s.lastRefreshAt ? "，最近檢查 " + formatSessionTime(s.lastRefreshAt) : ""}`;
    stateKind = "warn";
  } else {
    stateText = "可能過期或資料不足，請按刷新 Session";
    stateKind = "warn";
  }
  if (sessionStateEl) sessionStateEl.textContent = stateText;
  const sessionMiniText = `Session ${stateKind === "ok" ? "可用" : stateKind === "bad" ? "需重新匯入" : "尚未確認"}`;
  sessionMiniEl.textContent = sessionMiniText;
  sessionMiniStatusEl.setAttribute("aria-label", sessionMiniText);
  sessionMiniStatusEl.title = sessionMiniText;
  sessionDotEl.className = `dot ${stateKind}`;
  sessionIndicatorEl.className = `session-indicator ${stateKind}`;
}

// ---------- auto refresh ----------
function secondsUntilNextRefresh(config = lastAutoRefresh) {
  if (!config || !config.enabled) return null;
  const interval = Number(config.intervalSeconds || 600);
  if (config.nextRunAt) return Math.max(0, Math.ceil(Number(config.nextRunAt) - Date.now() / 1000));
  if (config.remainingSeconds !== null && config.remainingSeconds !== undefined) {
    const baseNow = Number(config.serverNow || Date.now() / 1000);
    return Math.max(0, Math.ceil(baseNow + Number(config.remainingSeconds || 0) - Date.now() / 1000));
  }
  const lastRun = Number(config.lastRunAt || config.lastSuccessAt || 0);
  return lastRun ? Math.max(0, Math.ceil(lastRun + interval - Date.now() / 1000)) : interval;
}
function formatCountdown(seconds) {
  if (seconds === null || seconds === undefined) return "關閉";
  const s = Math.max(0, Number(seconds) || 0);
  if (s < 60) return `${s} 秒後`;
  if (s < 3600) return `${Math.round(s / 60)} 分後`;
  return `${Math.round(s / 3600)} 小時後`;
}
function updateAutoRefreshButton() {
  if (!lastAutoRefresh || !lastAutoRefresh.enabled) {
    setAutoRefreshMini("自動刷新 關閉", lastAutoRefresh && (lastAutoRefresh.disabledReason || lastAutoRefresh.lastError) ? "bad" : "warn");
    return;
  }
  const seconds = secondsUntilNextRefresh(lastAutoRefresh);
  setAutoRefreshMini(seconds <= 0 ? "自動刷新 執行中" : `自動刷新 ${formatCountdown(seconds)}`, seconds <= 0 ? "warn" : "ok");
  if (seconds <= 0 && !lastAutoRefresh._reloading) {
    lastAutoRefresh._reloading = true;
    window.setTimeout(async () => { await loadAutoRefresh(); if (lastAutoRefresh) lastAutoRefresh._reloading = false; }, 30000);
  }
}
function setAutoRefreshMini(text, stateKind) {
  autoRefreshMiniEl.textContent = text;
  autoRefreshMiniEl.setAttribute("aria-label", text);
  autoRefreshMiniEl.title = text;
  autoRefreshMiniEl.classList.remove("ok", "warn", "bad");
  autoRefreshMiniEl.classList.add(stateKind);
}
function startAutoRefreshCountdown() {
  if (autoRefreshCountdownTimer !== null) window.clearInterval(autoRefreshCountdownTimer);
  autoRefreshCountdownTimer = window.setInterval(updateAutoRefreshButton, 1000);
  updateAutoRefreshButton();
}
function renderAutoRefresh(config = lastAutoRefresh) {
  lastAutoRefresh = config || lastAutoRefresh || {};
  const c = lastAutoRefresh;
  if (autoRefreshEnabledEl) {
    autoRefreshEnabledEl.checked = Boolean(c.enabled);
    autoRefreshIntervalEl.value = c.intervalSeconds || 600;
    const parts = [c.enabled ? `已啟用，${formatCountdown(secondsUntilNextRefresh(c))}` : "已關閉"];
    if (c.workerRunning !== undefined) parts.push(`worker ${c.workerRunning ? "運行中" : "未運行"}`);
    if (c.lastSuccessAt) parts.push(`最近成功 ${formatSessionTime(c.lastSuccessAt)}`);
    if (c.disabledReason) parts.push(`關閉原因：${c.disabledReason}`);
    else if (c.lastError) parts.push(`錯誤：${c.lastError}`);
    autoRefreshStatusEl.textContent = parts.join(" · ");
  }
  startAutoRefreshCountdown();
}
async function loadAutoRefresh() {
  try {
    const response = await fetch("/v1/auto-refresh", { headers: apiHeaders() });
    const data = await response.json();
    if (response.ok && data.ok && data.data) renderAutoRefresh(data.data);
    return data;
  } catch (error) {
    if (autoRefreshStatusEl) autoRefreshStatusEl.textContent = `載入失敗：${String(error)}`;
    return null;
  }
}
async function saveAutoRefreshSettings() {
  const payload = { enabled: autoRefreshEnabledEl.checked, intervalSeconds: Number(autoRefreshIntervalEl.value || 600) };
  const data = await request("/v1/auto-refresh", { method: "POST", headers: apiHeaders(), body: JSON.stringify(payload) });
  if (data && data.data) { renderAutoRefresh(data.data); toast("自動刷新設定已保存", "ok"); }
  return data;
}
async function runAutoRefreshNow() {
  const data = await request("/v1/auto-refresh/run", { method: "POST", headers: apiHeaders(), body: "{}" });
  if (data && data.data && data.data.autoRefresh) {
    renderAutoRefresh(data.data.autoRefresh);
    if (data.data.session) { renderSessionInfo(data.data.session); }
    if (data.data.session && data.data.session.sessionValid) { await refreshAliasTable(); toast("手動刷新成功，清單已同步", "ok"); }
  }
  return data;
}

// ---------- API Builder ----------
function setSelectedOperation(operationName) {
  currentOperation = operations[operationName] ? operationName : "list";
  endpointList.querySelectorAll("[data-endpoint]").forEach((button) => {
    const isActive = button.dataset.endpoint === currentOperation;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
  syncRequestPreview();
  showResponseExample();
}
function requestTemplate(operationName = currentOperation) {
  const operation = operations[operationName] || operations.list;
  return {
    method: operation.method,
    path: operation.path,
    headers: { "X-API-Key": readApiKey() || API_KEY_PLACEHOLDER, ...(operation.body ? { "Content-Type": "application/json" } : {}) },
    body: operation.body
  };
}
function syncRequestPreview() {
  const requestData = requestTemplate();
  methodBadge.textContent = requestData.method;
  requestPreviewEl.value = JSON.stringify(requestData, null, 2);
  responsePreviewEl.textContent = JSON.stringify(responseExamples[currentOperation] || responseExamples.list, null, 2);
  syncCurlFromRequestEditor();
}
function showCurl(method, path, body, headers = {}) {
  const key = headers["X-API-Key"] || headers["x-api-key"] || readApiKey() || API_KEY_PLACEHOLDER;
  const bodyPart = body ? ` \\\n  -H "Content-Type: application/json" \\\n  --data '${JSON.stringify(body)}'` : "";
  curlOutputEl.textContent = `curl -X ${method} "http://127.0.0.1:8000${path}" \\\n  -H "X-API-Key: ${key}"${bodyPart}`;
}
function readRequestJson(validate = false) {
  try {
    const data = JSON.parse(requestPreviewEl.value || "{}");
    if (validate && (!data.method || !data.path)) throw new Error("method and path are required");
    if (validate && (String(data.path).includes("{anonymousId}") || String(data.path).includes("{guid}"))) {
      show({ ok: false, data: null, error: { code: "MISSING_PATH_PARAM", message: "請先把 path 的 {anonymousId} / {guid} 換成真實 ID。" }, meta: META }, true);
      throw new Error("MISSING_PATH_PARAM");
    }
    return data;
  } catch (error) {
    if (validate && String(error.message || error) === "MISSING_PATH_PARAM") throw error;
    if (validate) {
      show({ ok: false, data: null, error: { code: "INVALID_REQUEST_JSON", message: `API Request JSON 格式錯誤：${String(error.message || error)}` }, meta: META }, true);
      throw error;
    }
    return null;
  }
}
function syncCurlFromRequestEditor() {
  const requestData = readRequestJson(false);
  if (!requestData) { curlOutputEl.textContent = "API Request JSON 格式錯誤，修正後會自動同步 curl。"; return; }
  methodBadge.textContent = requestData.method || "GET";
  showCurl(requestData.method || "GET", requestData.path || "/v1/aliases", requestData.body, requestData.headers || {});
}
async function runSelectedOperation(operationName = null) {
  if (operationName) setSelectedOperation(operationName);
  else syncCurlFromRequestEditor();
  const requestData = readRequestJson(true);
  const activeOperation = operationName || currentOperation;
  const path = String(requestData.path || "");
  if (path.includes("/delete") && !window.confirm(`確定要刪除 ${path} 指定的隱私信箱？此操作不可復原。`)) return null;
  const headers = { ...(requestData.headers || {}) };
  if (!headers["X-API-Key"] && !headers["x-api-key"]) headers["X-API-Key"] = readApiKey();
  if (requestData.body != null && !headers["Content-Type"] && !headers["content-type"]) headers["Content-Type"] = "application/json";
  const data = await request(requestData.path, {
    method: requestData.method,
    headers,
    body: requestData.body != null ? JSON.stringify(requestData.body) : undefined
  });
  if (data && data.data && activeOperation === "list") { setAliasRows(data.data); }
  if (data && data.data && activeOperation === "refresh") {
    lastSessionRefreshAt = data.data.lastRefreshAt || new Date();
    renderSessionInfo(data.data);
    if (data.data.needsReauth) { toast("Session 需要重新匯入", "bad"); return data; }
    if (data.data.sessionValid) { await refreshAliasTable(); toast("Session 已刷新，清單已同步", "ok"); }
  }
  if (data && data.data && ["create", "disable", "enable", "delete"].includes(activeOperation)) await refreshAliasTable();
  return data;
}

// ---------- aliases ----------
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}
function filterAliases(aliases) {
  const keyword = (aliasFilterInput.value || "").trim().toLowerCase();
  if (!keyword) return aliases;
  return aliases.filter((alias) => [alias.hme, alias.anonymousId, alias.label, alias.note, alias.forwardToEmail, alias.isActive ? "active" : "inactive"]
    .some((value) => String(value || "").toLowerCase().includes(keyword)));
}
function setAliasRows(rows) {
  aliasRows = Array.isArray(rows) ? rows : [];
  aliasesLoadedOnce = true;
  lastAliasSyncAt = new Date();
  renderAliases();
  renderSessionInfo();
  if (inboxLoadedOnce) renderMailAliasOptions();
}
function renderAliases() {
  aliasSourceEl.textContent = JSON.stringify(aliasRows || [], null, 2);
  if (aliasCountSub) aliasCountSub.textContent = `${aliasRows.length} 筆`;
  const filtered = filterAliases(aliasRows);
  if (!filtered.length) {
    let hint;
    if (!aliasesLoadedOnce) hint = "載入信箱清單中…";
    else if (aliasRows.length) hint = "沒有符合搜尋的信箱。";
    else hint = '目前沒有信箱資料。請至「Session &amp; 自動刷新」匯入或刷新 Session，再按「重新整理」。';
    tableEl.innerHTML = `<div class="empty-state">${hint}</div>`;
    return;
  }
  const rows = filtered.map((alias, index) => {
    const active = alias.isActive;
    const toggleAction = active ? "disable" : "enable";
    const toggleLabel = active ? "停用" : "啟用";
    const created = alias.createTimestamp ? new Date(Number(alias.createTimestamp)).toLocaleString() : "";
    return `<tr>
      <td class="mono hme-cell">
        <button type="button" class="copy-btn" data-action="copy-alias" data-index="${index}" title="複製信箱地址" aria-label="複製信箱地址">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button><span>${escapeHtml(alias.hme || "")}</span>
      </td>
      <td>${escapeHtml(alias.label || "")}</td>
      <td>${escapeHtml(alias.note || "")}</td>
      <td class="mono">${escapeHtml(alias.forwardToEmail || "")}</td>
      <td class="mono created-cell">${escapeHtml(created)}</td>
      <td><span class="badge ${active ? "on" : "off"}">${active ? "active" : "inactive"}</span></td>
      <td class="row-actions">
        <button type="button" data-action="inbox-alias" data-index="${index}" title="查看此信箱的收件">收件</button>
        <button type="button" data-action="toggle-alias" data-index="${index}" data-alias-action="${toggleAction}">${toggleLabel}</button>
        <button type="button" class="danger" data-action="delete-alias" data-index="${index}">刪除</button>
      </td></tr>`;
  }).join("");
  tableEl.innerHTML = `<table>
      <thead><tr><th>hme</th><th>label</th><th>note</th><th>forwardTo</th><th>建立時間</th><th>status</th><th>操作</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
}
async function refreshAliasTable() {
  try {
    const response = await fetch("/v1/aliases", { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return null; }
    const data = await response.json();
    if (response.ok && data.ok !== false && data.data) setAliasRows(data.data);
    return data;
  } catch (error) {
    setStatus("清單刷新失敗", true);
    return null;
  } finally {
    if (!aliasesLoadedOnce) { aliasesLoadedOnce = true; renderAliases(); }
  }
}
async function runAliasAction(alias, action) {
  showActualOutput({ running: true, action, anonymousId: alias.anonymousId });
  const data = await request(`/v1/aliases/${encodeURIComponent(alias.anonymousId || "")}/${action}`, {
    method: "POST",
    headers: apiHeaders()
  });
  await refreshAliasTable();
  return data;
}
async function submitCreateAlias(event) {
  event.preventDefault();
  const label = ($("createLabel").value || "").trim();
  if (!label) { toast("label 為必填", "bad"); return; }
  const note = $("createNote").value || "";
  const submitBtn = $("createSubmitBtn");
  submitBtn.disabled = true;
  submitBtn.textContent = "建立中…";
  try {
    const data = await request("/v1/aliases", { method: "POST", headers: apiHeaders(), body: JSON.stringify({ label, note }) });
    if (data && data.data) {
      $("createLabel").value = "";
      $("createNote").value = "";
      createAliasForm.hidden = true;
      toast(`已建立 ${data.data.hme || label}，已複製到剪貼簿`, "ok");
      if (data.data.hme) copyText(data.data.hme, "已複製新信箱");
      await refreshAliasTable();
    }
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "建立";
  }
}

async function exportAliasesCsv() {
  try {
    const response = await fetch("/v1/aliases/export.csv", { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return; }
    const data = await response.json();
    if (!response.ok || data.ok === false || typeof data.data !== "string") {
      show(data, true);
      return;
    }
    const blob = new Blob(["\ufeff" + data.data], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `hme-aliases-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    toast("CSV 已匯出", "ok");
  } catch (error) {
    toast(`匯出失敗：${String(error)}`, "bad");
  }
}

// ---------- inbox ----------
function formatMailTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "numeric", day: "numeric" }) + " " + date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function extractVerificationCode(message) {
  const haystacks = [message.subject || "", message.snippet || "", message.textBody || "", (message.htmlBody || "").replace(/<[^>]+>/g, " ")];
  const labelled = /(?:code|verification|one[- ]?time|otp|pin|驗證碼|验证码|校驗碼|校验码|動態密碼|动态密码)\D{0,20}?(\d{4,8})/i;
  for (const text of haystacks) {
    const match = text.match(labelled);
    if (match) return match[1];
  }
  for (const text of haystacks) {
    const match = text.match(/(?:^|\s)(\d{6})(?:\s|$|[.,!])/);
    if (match) return match[1];
  }
  return null;
}

function renderMailFolders() {
  if (!mailFolderSelect) return;
  if (!mailFolders.length) {
    mailFolderSelect.innerHTML = '<option value="">找不到資料夾</option>';
    return;
  }
  mailFolderSelect.innerHTML = mailFolders.map((folder) => {
    const unread = folder.unreadCount ? `（${folder.unreadCount} 未讀）` : "";
    return `<option value="${escapeHtml(folder.guid)}">${escapeHtml(folder.name)}${unread}</option>`;
  }).join("");
  const inbox = mailFolders.find((folder) => String(folder.role || "").toUpperCase() === "INBOX")
    || mailFolders.find((folder) => /inbox|收件/i.test(folder.name || ""))
    || mailFolders[0];
  mailFolderSelect.value = inbox.guid;
}

function renderMailAliasOptions() {
  if (!mailAliasSelect) return;
  const options = ['<option value="">全部郵件</option>'];
  aliasRows.forEach((alias) => {
    if (!alias.hme) return;
    const label = alias.label ? `${alias.label} — ${alias.hme}` : alias.hme;
    options.push(`<option value="${escapeHtml(alias.hme)}">${escapeHtml(label)}</option>`);
  });
  mailAliasSelect.innerHTML = options.join("");
  mailAliasSelect.value = mailAliasFilter;
  if (mailAliasSelect.value !== mailAliasFilter) {
    // filter address is not in the alias list (e.g. deleted); keep it selectable
    mailAliasSelect.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(mailAliasFilter)}">${escapeHtml(mailAliasFilter)}</option>`);
    mailAliasSelect.value = mailAliasFilter;
  }
}

function mailLoadMoreHtml() {
  if (!mailTotal || mailAllMessages.length >= mailTotal) return "";
  return `<button type="button" class="load-more" data-action="load-more-mail">載入更早的郵件（已快取 ${mailAllMessages.length}/${mailTotal}）</button>`;
}

function renderMailList() {
  if (!mailListEl) return;
  if (!mailMessages.length) {
    const empty = mailAliasFilter
      ? `<div class="empty-state">此信箱在已快取的 ${mailAllMessages.length} 封中沒有收件。<br><small class="mono">${escapeHtml(mailAliasFilter)}</small></div>`
      : '<div class="empty-state">此資料夾沒有郵件。</div>';
    mailListEl.innerHTML = empty + mailLoadMoreHtml();
    return;
  }
  mailListEl.innerHTML = mailMessages.map((message, index) => `
    <button type="button" class="mail-item${message.guid === currentMailGuid ? " active" : ""}${message.isRead === false ? " unread" : ""}" data-mail-index="${index}">
      <span class="mail-item-top"><span class="mail-from">${escapeHtml(message.from || "(未知寄件人)")}</span><span class="mail-date">${escapeHtml(formatMailTime(message.date))}</span></span>
      <span class="mail-subject">${escapeHtml(message.subject || "(無主旨)")}</span>
      ${message.snippet ? `<span class="mail-snippet">${escapeHtml(message.snippet)}</span>` : ""}
    </button>`).join("") + mailLoadMoreHtml();
}

function applyMailFilter() {
  const key = (mailAliasFilter || "").trim().toLowerCase();
  mailMessages = key
    ? mailAllMessages.filter((message) => String(message.to || "").toLowerCase().includes(key))
    : mailAllMessages.slice();
  renderMailList();
  const at = mailCacheAt ? mailCacheAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
  setStatus(key
    ? `顯示 ${mailMessages.length} 封（快取 ${mailAllMessages.length} 封 · ${at}）`
    : `已快取 ${mailAllMessages.length} 封（${at}）`);
}

function renderMailReader(message) {
  if (!mailReaderEl) return;
  if (!message) {
    mailReaderEl.innerHTML = '<div class="empty-state">從左側選擇一封郵件即可閱讀內容；偵測到驗證碼時可一鍵複製。</div>';
    return;
  }
  const code = extractVerificationCode(message);
  const attachments = Array.isArray(message.attachments) && message.attachments.length
    ? `<div class="mail-attachments">附件：${message.attachments.map((a) => escapeHtml(a.filename || "(未命名)")).join("、")}</div>`
    : "";
  let bodyHtml;
  if (message.htmlBody) {
    bodyHtml = `<iframe class="mail-html" sandbox="" referrerpolicy="no-referrer" title="郵件內容"></iframe>`;
  } else if (message.textBody) {
    bodyHtml = `<pre class="mail-text">${escapeHtml(message.textBody)}</pre>`;
  } else {
    bodyHtml = '<div class="empty-state">（此郵件沒有可顯示的內容）</div>';
  }
  mailReaderEl.innerHTML = `
    <div class="mail-head">
      <div class="mail-head-subject">${escapeHtml(message.subject || "(無主旨)")}</div>
      <dl class="mail-meta">
        <dt>寄件人</dt><dd>${escapeHtml(message.from || "未知")}</dd>
        <dt>收件人</dt><dd class="mono">${escapeHtml(message.to || "未知")}</dd>
        <dt>時間</dt><dd>${escapeHtml(message.date ? new Date(message.date).toLocaleString() : "未知")}</dd>
      </dl>
      ${code ? `<button type="button" class="code-chip" data-code="${escapeHtml(code)}" title="點擊複製驗證碼">驗證碼 <strong>${escapeHtml(code)}</strong>（點擊複製）</button>` : ""}
      ${attachments}
    </div>
    ${bodyHtml}`;
  const frame = mailReaderEl.querySelector("iframe.mail-html");
  if (frame && message.htmlBody) frame.srcdoc = message.htmlBody;
  const chip = mailReaderEl.querySelector(".code-chip");
  if (chip) chip.addEventListener("click", () => copyText(chip.dataset.code, "已複製驗證碼"));
}

async function loadMailFolders() {
  try {
    const response = await fetch("/v1/mail/folders", { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return false; }
    const data = await response.json();
    if (!response.ok || data.ok === false || !Array.isArray(data.data)) {
      renderMailError(data);
      return false;
    }
    mailFolders = data.data;
    renderMailFolders();
    return true;
  } catch (error) {
    renderMailError({ error: { message: String(error) } });
    return false;
  }
}

async function loadMailMessages(force = false) {
  const folder = mailFolderSelect ? mailFolderSelect.value : "";
  if (!folder) return;
  // Same folder already cached: filter locally, no network round-trip.
  if (!force && folder === mailCacheFolder && mailAllMessages.length) {
    applyMailFilter();
    return;
  }
  mailListEl.innerHTML = '<div class="empty-state">載入郵件中…</div>';
  try {
    const response = await fetch(`/v1/mail/messages?folder=${encodeURIComponent(folder)}&limit=100`, { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return; }
    const data = await response.json();
    if (!response.ok || data.ok === false || !data.data) {
      renderMailError(data);
      return;
    }
    mailAllMessages = Array.isArray(data.data.messages) ? data.data.messages : [];
    mailCacheFolder = folder;
    mailCacheAt = new Date();
    const total = Number(data.data.total);
    mailTotal = Number.isFinite(total) ? total : null;
    mailDetailCache.clear();
    currentMailGuid = null;
    applyMailFilter();
    renderMailReader(null);
  } catch (error) {
    renderMailError({ error: { message: String(error) } });
  }
}

async function loadMoreMailMessages(button) {
  if (!mailCacheFolder) return;
  if (button) { button.disabled = true; button.textContent = "載入中…"; }
  try {
    const offset = mailAllMessages.length;
    const response = await fetch(`/v1/mail/messages?folder=${encodeURIComponent(mailCacheFolder)}&limit=100&offset=${offset}`, { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return; }
    const data = await response.json();
    if (!response.ok || data.ok === false || !data.data) { renderMailError(data); return; }
    const known = new Set(mailAllMessages.map((message) => message.guid));
    const fresh = (Array.isArray(data.data.messages) ? data.data.messages : []).filter((message) => !known.has(message.guid));
    mailAllMessages = mailAllMessages.concat(fresh);
    const total = Number(data.data.total);
    if (Number.isFinite(total)) mailTotal = total;
    if (!fresh.length) mailTotal = mailAllMessages.length; // server has no more for us
    applyMailFilter();
  } catch (error) {
    toast(`載入更多失敗：${String(error)}`, "bad");
    renderMailList();
  }
}

async function openMailMessage(index) {
  const summary = mailMessages[index];
  if (!summary || !summary.guid) return;
  currentMailGuid = summary.guid;
  renderMailList();
  const cached = mailDetailCache.get(summary.guid);
  if (cached) { renderMailReader({ ...summary, ...cached }); return; }
  mailReaderEl.innerHTML = '<div class="empty-state">讀取郵件中…</div>';
  try {
    const response = await fetch(`/v1/mail/messages/${encodeURIComponent(summary.guid)}`, { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return; }
    const data = await response.json();
    if (!response.ok || data.ok === false || !data.data) {
      renderMailReader({ ...summary, textBody: "", htmlBody: "" });
      toast(data && data.error && data.error.message ? data.error.message : "讀取郵件失敗，僅顯示摘要", "warn");
      return;
    }
    mailDetailCache.set(summary.guid, data.data);
    renderMailReader({ ...summary, ...data.data });
  } catch (error) {
    toast(`讀取郵件失敗：${String(error)}`, "bad");
  }
}

function renderMailError(data) {
  const message = data && data.error && (data.error.message || data.error.code) ? (data.error.message || data.error.code) : "載入失敗";
  const hint = /SESSION_MISSING|尚未匯入/.test(String(message))
    ? "請先在「Session & 自動刷新」匯入 Session。"
    : "若持續失敗，請在 iCloud 網頁開啟過「郵件」後重新匯入 Session（需要郵件授權 cookie）。";
  mailListEl.innerHTML = `<div class="empty-state">${escapeHtml(String(message))}<br><small>${escapeHtml(hint)}</small></div>`;
}

async function initInbox() {
  if (!mailFolderSelect) return;
  if (!aliasRows.length) await refreshAliasTable();
  renderMailAliasOptions();
  const loaded = await loadMailFolders();
  if (loaded) await loadMailMessages();
}

async function openInboxForAlias(hme) {
  mailAliasFilter = String(hme || "");
  if (inboxLoadedOnce) {
    renderMailAliasOptions();
    showView("inbox");
    await loadMailMessages(); // cached folder → instant local filter
  } else {
    showView("inbox"); // initInbox picks up mailAliasFilter
  }
}

function resetMailCache() {
  mailAllMessages = [];
  mailMessages = [];
  mailCacheFolder = null;
  mailCacheAt = null;
  mailTotal = null;
  mailDetailCache.clear();
  currentMailGuid = null;
}

// ---------- session actions ----------
async function loadStatus() {
  try {
    const response = await fetch("/v1/session/status", { headers: apiHeaders() });
    if (response.status === 401) { showModal(); return; }
    const data = await response.json();
    if (data && data.data) renderSessionInfo(data.data);
  } catch (error) { /* keep prior status */ }
}

async function submitImportSession() {
  const curlText = ($("importCurl").value || "").trim();
  const resultEl = $("importResult");
  resultEl.hidden = false;
  if (!curlText) { resultEl.textContent = "請先貼上 list?clientBuildNumber 請求的 Copy as cURL (bash) 或 HAR JSON。"; return; }
  resultEl.textContent = "匯入中…";
  const data = await request("/v1/session/import", {
    method: "POST",
    headers: apiHeaders(),
    body: JSON.stringify({ curl_text: curlText })
  });
  if (!data) { resultEl.textContent = "匯入失敗，請確認貼上的內容包含 cookie。"; return; }
  resultEl.textContent = JSON.stringify(data.data, null, 2);
  $("importCurl").value = "";
  const importedRegion = data.data && data.data.region === "china" ? "中國大陸（icloud.com.cn）" : "全球（icloud.com）";
  toast(`Session 已匯入（${importedRegion}），正在刷新與同步…`, "ok");
  inboxLoadedOnce = false; // next visit to inbox reloads with the new session
  resetMailCache();
  await runSelectedOperation("refresh");
  await loadStatus();
  await refreshAliasTable();
}

// ---------- API Key modal ----------
const apiKeyModal = $("apiKeyModal");
const modalApiKeyInput = $("modalApiKeyInput");
const modalError = $("modalError");
function showModal() {
  apiKeyModal.classList.remove("hidden");
  modalError.style.display = "none";
  modalApiKeyInput.value = "";
  modalApiKeyInput.focus();
}
function hideModal() { apiKeyModal.classList.add("hidden"); }
async function verifyApiKey(key) {
  try {
    const res = await fetch("/v1/session/status", { headers: { "X-API-Key": key } });
    return res.status !== 401;
  } catch { return false; }
}
async function handleModalSubmit() {
  const key = modalApiKeyInput.value.trim();
  if (!key) { modalError.style.display = "block"; modalError.textContent = "請輸入 API Key"; return; }
  if (await verifyApiKey(key)) { setStoredApiKey(key); hideModal(); init(); }
  else { modalError.style.display = "block"; modalError.textContent = "API Key 無效"; }
}

// ---------- wiring ----------
document.querySelectorAll("[data-view]").forEach((el) => el.addEventListener("click", () => showView(el.dataset.view)));
$("logoutBtn").addEventListener("click", () => { localStorage.removeItem(STORAGE_KEY); showModal(); });

aliasFilterInput.addEventListener("input", renderAliases);
$("refreshListBtn").addEventListener("click", refreshAliasTable);
$("exportCsvBtn").addEventListener("click", exportAliasesCsv);
$("refreshMailBtn").addEventListener("click", async () => { await loadMailFolders(); await loadMailMessages(true); });
mailFolderSelect.addEventListener("change", () => loadMailMessages());
mailAliasSelect.addEventListener("change", () => {
  mailAliasFilter = mailAliasSelect.value || "";
  if (mailCacheFolder && mailAllMessages.length) applyMailFilter(); // instant, no refetch
  else loadMailMessages();
});
mailListEl.addEventListener("click", (event) => {
  const moreButton = event.target.closest('[data-action="load-more-mail"]');
  if (moreButton) { loadMoreMailMessages(moreButton); return; }
  const item = event.target.closest("[data-mail-index]");
  if (item) openMailMessage(Number(item.dataset.mailIndex));
});
$("createAliasBtn").addEventListener("click", () => {
  createAliasForm.hidden = !createAliasForm.hidden;
  if (!createAliasForm.hidden) $("createLabel").focus();
});
$("createCancelBtn").addEventListener("click", () => { createAliasForm.hidden = true; });
createAliasForm.addEventListener("submit", submitCreateAlias);
aliasTabs.addEventListener("click", (event) => {
  const button = event.target.closest("[data-alias-tab]");
  if (!button) return;
  const source = button.dataset.aliasTab === "source";
  aliasTabs.querySelectorAll("[data-alias-tab]").forEach((b) => {
    const on = b === button;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  tableEl.hidden = source;
  aliasSourceEl.hidden = !source;
});
tableEl.addEventListener("click", async (event) => {
  const copyButton = event.target.closest('[data-action="copy-alias"]');
  const inboxButton = event.target.closest('[data-action="inbox-alias"]');
  const toggleButton = event.target.closest('[data-action="toggle-alias"]');
  const deleteButton = event.target.closest('[data-action="delete-alias"]');
  const button = copyButton || inboxButton || toggleButton || deleteButton;
  if (!button) return;
  const alias = filterAliases(aliasRows)[Number(button.dataset.index)];
  if (!alias) return;
  if (copyButton) { await copyText(alias.hme || "", "已複製信箱"); return; }
  if (inboxButton) { await openInboxForAlias(alias.hme || ""); return; }
  if (!alias.anonymousId) return;
  if (toggleButton) {
    const action = toggleButton.dataset.aliasAction || "disable";
    const data = await runAliasAction(alias, action);
    if (data && data.ok !== false) toast(`${action === "disable" ? "已停用" : "已啟用"} ${alias.hme || alias.anonymousId}`, "ok");
    return;
  }
  if (!window.confirm(`確定要停用並刪除 ${alias.hme || alias.anonymousId}？此操作不可復原。`)) return;
  if (alias.isActive) await runAliasAction(alias, "disable");
  const data = await runAliasAction(alias, "delete");
  if (data && data.ok !== false) toast(`已刪除 ${alias.hme || alias.anonymousId}`, "ok");
});

endpointList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-endpoint]");
  if (button) setSelectedOperation(button.dataset.endpoint);
});
requestPreviewEl.addEventListener("input", syncCurlFromRequestEditor);
$("sendBtn").addEventListener("click", () => runSelectedOperation());

$("refreshSessionBtn").addEventListener("click", () => runSelectedOperation("refresh"));
$("saveAutoRefreshBtn").addEventListener("click", saveAutoRefreshSettings);
$("runAutoRefreshBtn").addEventListener("click", runAutoRefreshNow);
$("importSubmitBtn").addEventListener("click", submitImportSession);

// ---------- theme toggle ----------
const THEME_KEY = "hme-theme";
const themeToggle = $("themeToggle");
function effectiveTheme() {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function updateThemeIcon() {
  const dark = effectiveTheme() === "dark";
  themeToggle.querySelector(".ico-sun").hidden = !dark;
  themeToggle.querySelector(".ico-moon").hidden = dark;
}
function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  updateThemeIcon();
}
themeToggle.addEventListener("click", toggleTheme);
updateThemeIcon();
modalApiKeyInput.addEventListener("keydown", (event) => { if (event.key === "Enter") handleModalSubmit(); });
$("modalSubmitBtn").addEventListener("click", handleModalSubmit);

// ---------- init ----------
function init() {
  setSelectedOperation("list");
  const initialView = (window.location.hash || "").replace("#", "");
  showView(VIEW_TITLES[initialView] ? initialView : "aliases");
  loadAutoRefresh();
  loadStatus();
}

(async () => {
  const stored = getStoredApiKey();
  if (stored && (await verifyApiKey(stored))) { hideModal(); init(); }
  else showModal();
})();
