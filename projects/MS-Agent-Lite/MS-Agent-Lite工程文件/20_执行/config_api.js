// config_api.js — provider 配置读写（20_执行/config.json）+ 连通性自检
// 供 server.js 的 /api/providers* 路由使用；格式与现有 config.json 完全兼容
const fs = require("fs");
const path = require("path");
const { loadConfig, availableProviders, askText } = require("./llm_gateway.js");

const CONFIG_PATH = path.join(__dirname, "config.json");

function readConfig() {
  let raw;
  try { raw = fs.readFileSync(CONFIG_PATH, "utf8"); }
  catch (e) {
    // 首次运行/未配置：GitHub 分发版不含 config.json，返回空配置，保存时自动创建
    if (e.code === "ENOENT") return { providers: [] };
    throw new Error("config.json 读取失败: " + e.message);
  }
  try { return JSON.parse(raw); }
  catch (e) {
    // 文件损坏：备份坏文件后返回空配置，避免整个服务崩溃
    try { fs.renameSync(CONFIG_PATH, CONFIG_PATH + ".bak-" + Date.now()); } catch (e2) {}
    return { providers: [] };
  }
}
function writeConfig(cfg) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2) + "\n", "utf8");
}

// 脱敏：apiKey 仅显示后 4 位
function maskKey(key) {
  if (!key) return "";
  if (key.length <= 8) return "****" + key.slice(-4);
  return key.slice(0, 4) + "****" + key.slice(-4);
}

// getProviders() → 脱敏列表（不含真实 apiKey）
function getProviders() {
  const cfg = readConfig();
  const arr = Array.isArray(cfg.providers) ? cfg.providers
    : (cfg.provider ? [{ name: cfg.provider, baseUrl: cfg.baseUrls && cfg.baseUrls[cfg.provider],
        model: cfg.models && cfg.models[cfg.provider], apiKey: cfg.apiKey, enabled: true }] : []);
  return arr.map(p => ({
    name: p.name, baseUrl: p.baseUrl, model: p.model, displayName: p.displayName || "",
    apiKeyMasked: maskKey(p.apiKey), hasKey: !!(p.apiKey && p.apiKey.length > 0),
    enabled: p.enabled !== false, cap: p.cap || [], maxOutputTokens: p.maxOutputTokens || null
  }));
}

// saveProvider(p) — 新增或更新（p.apiKey 为空时保留旧 key，便于仅改其他字段）
function saveProvider(p) {
  if (!p || !p.name || !p.baseUrl || !p.model) {
    // 明确告知缺哪项、去哪填（界面已有字段级提示，这里是后端兜底）
    const missing = [];
    if (!p || !p.name) missing.push("配置名称");
    if (!p || !p.baseUrl) missing.push("Base URL");
    if (!p || !p.model) missing.push("模型名");
    throw new Error("缺少必填项：" + missing.join("、") + "——可先在上方①选择平台自动填入，再核对修改");
  }
  const cfg = readConfig();
  const arr = Array.isArray(cfg.providers) ? cfg.providers : [];
  const idx = arr.findIndex(x => x.name === p.name);
  if (idx >= 0) {
    const prev = arr[idx];
    // apiKey 语义（P2-6）：留空 → 保留旧 key（仅改其他字段）；传了但 <5 字符 → 明确报错，防误输入垃圾 key 覆盖真实 key
    let apiKey = prev.apiKey;
    if (p.apiKey !== undefined && p.apiKey !== "") {
      if (p.apiKey.length < 5) throw new Error("apiKey 长度不足（≥5 字符）——请粘贴完整 API Key；若只是修改其他字段，请留空 apiKey 输入框");
      apiKey = p.apiKey;
    }
    arr[idx] = {
      ...prev,
      baseUrl: p.baseUrl, model: p.model,
      apiKey,
      enabled: p.enabled !== undefined ? !!p.enabled : prev.enabled !== false,
      cap: p.cap || prev.cap || [], maxOutputTokens: p.maxOutputTokens !== undefined ? p.maxOutputTokens : prev.maxOutputTokens,
      displayName: p.displayName !== undefined ? (p.displayName || "") : (prev.displayName || "")
    };
  } else {
    if (!p.apiKey || p.apiKey.length < 5) throw new Error("新增 provider 必须提供 apiKey");
    arr.push({ name: p.name, baseUrl: p.baseUrl, model: p.model, apiKey: p.apiKey,
      enabled: p.enabled !== undefined ? !!p.enabled : true, cap: p.cap || [], maxOutputTokens: p.maxOutputTokens || null,
      displayName: p.displayName || "" });
  }
  cfg.providers = arr;
  writeConfig(cfg);
  return getProviders();
}

// deleteProvider(name)
function deleteProvider(name) {
  const cfg = readConfig();
  if (Array.isArray(cfg.providers)) {
    cfg.providers = cfg.providers.filter(x => x.name !== name);
    writeConfig(cfg);
  }
  return getProviders();
}

// testProvider(name, {real}) — 自检
//   real=false（默认）：配置校验（cap 过滤链是否可用）
//   real=true：发一个最小请求验证连通性（max_tokens=64，提示词固定）
async function testProvider(name, opts = {}) {
  const cfg = readConfig();
  const arr = Array.isArray(cfg.providers) ? cfg.providers : [];
  const p = arr.find(x => x.name === name);
  if (!p) throw new Error("provider 不存在: " + name);
  const info = { name: p.name, model: p.model, baseUrl: p.baseUrl, enabled: p.enabled !== false,
    hasKey: !!(p.apiKey && p.apiKey.length > 0), caps: p.cap || [] };

  if (!opts.real) {
    const usable = availableProviders(arr, "text").some(x => x.name === name) ||
                   availableProviders(arr, "vision").some(x => x.name === name);
    return { ...info, ok: usable, mode: "config", detail: usable ? "配置有效（可用于生成）" : "配置未满足可用条件（需 enabled + apiKey + baseUrl + model）" };
  }

  // 真实最小请求（只测指定 provider，防链上其他 provider"顶包"——P1-10）
  // max_tokens=64：推理模型（如 DeepSeek-V4-Flash）的 reasoning 会吃 token，8 太小吃不下必致 content 为空
  const provs = availableProviders(arr, "text").filter(x => x.name === name);
  if (provs.length === 0) throw new Error("该 provider 配置未满足文本生成可用条件");
  const text = await askText("请只回复：OK", { maxTokens: 64, onLog: () => {}, onlyProvider: name });
  return { ...info, ok: true, mode: "real", detail: "真实请求成功，响应: " + String(text).slice(0, 40) };
}

// ---------- 联网搜索配置（v0.4.9，可选增强） ----------
// config.json 可选字段：{ "webSearch": { "provider": "tavily", "apiKey": "tvly-..." } }
// 设计：默认不配置（AI 按联网核实协议标注【待联网核实】项）；配置 Key 后管线自动搜索权威来源并注入上下文
function getWebSearchConfig() {
  const cfg = readConfig();
  const ws = cfg && cfg.webSearch;
  if (!ws || !ws.apiKey || !String(ws.apiKey).trim()) return null;
  return { provider: ws.provider || "tavily", apiKey: String(ws.apiKey).trim() };
}
// 脱敏状态（供 /api/web-search GET 展示，不下发真实 Key）
function getWebSearchStatus() {
  const cfg = getWebSearchConfig();
  if (!cfg) return { configured: false, provider: "" };
  return { configured: true, provider: cfg.provider, keyMasked: maskKey(cfg.apiKey) };
}
// 保存/关闭：apiKey 为空 → 删除 webSearch 字段（关闭联网搜索）
function saveWebSearch({ apiKey, provider } = {}) {
  const cfg = readConfig();
  const key = apiKey === undefined || apiKey === null ? "" : String(apiKey).trim();
  if (key) {
    // 与 saveProvider 一致的长度防线：防止误输短 Key 静默覆盖有效 Key（v0.4.9 代码审查修复）
    if (key.length < 5) throw new Error("apiKey 长度不足（≥5 字符）——请粘贴完整 Tavily API Key；留空保存可关闭联网搜索");
    cfg.webSearch = { provider: provider || "tavily", apiKey: key };
  } else {
    if (cfg.webSearch) delete cfg.webSearch;
  }
  writeConfig(cfg);
  return getWebSearchStatus();
}

module.exports = { getProviders, saveProvider, deleteProvider, testProvider, getWebSearchConfig, getWebSearchStatus, saveWebSearch };
