// llm_gateway.js — 多 provider LLM 网关（文本生成）
// 从 gen_material.js 抽出复用：cap 过滤、顺序即优先级、失败自动切换、超时、max_tokens 减半降级
// 供 pipeline.js / gen_material.js / 未来意图解析 共用同一网关
const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");

const TOOLS = __dirname;
// 请求超时（D2 修复）：硬编码 60s 过短，长 prompt（JD+简历+补充信息+组件）下 DeepSeek 等模型经常超 60s 被截断。
// 改为可配置：环境变量 MS_AGENT_TIMEOUT_MS（毫秒），默认 300000（5 分钟）。
const REQUEST_TIMEOUT_MS = parseInt(process.env.MS_AGENT_TIMEOUT_MS || "300000", 10) || 300000;

// ---------- config 加载（与 vision_analyze.js 同机制） ----------
function loadConfig() {
  const p = path.join(TOOLS, "config.json");
  let raw;
  try { raw = fs.readFileSync(p, "utf8"); }
  catch (e) {
    // 未配置（分发版不含 config.json）：返回空数组，由 availableProviders 给出"没有可用 provider"提示
    if (e.code === "ENOENT") return [];
    throw new Error("config.json 读取失败: " + e.message);
  }
  let cfg;
  try { cfg = JSON.parse(raw); }
  catch (e) { throw new Error("config.json 解析失败: " + e.message + "（可在网页第 1 步重新保存配置覆盖）"); }
  if (Array.isArray(cfg.providers)) return cfg.providers;
  if (cfg.provider) {
    return [{ name: cfg.provider, baseUrl: cfg.baseUrls && cfg.baseUrls[cfg.provider],
      model: cfg.models && cfg.models[cfg.provider], apiKey: cfg.apiKey, enabled: true }];
  }
  throw new Error("config.json 缺少 providers 数组");
}

// 按能力过滤 provider：cap 未设置视为兼容所有；文本生成只要含 "text" 的
function availableProviders(providers, cap) {
  return providers.filter(p =>
    p && p.enabled && p.apiKey && p.apiKey.length > 10 && p.baseUrl && p.model &&
    (!p.cap || p.cap.indexOf(cap) >= 0)
  );
}

// callText(provider, prompt, maxTokens, onLog, signal, system?)
// signal：可选 AbortSignal；abort 时立即 destroy 请求（配合任务取消，不空耗额度与等待）
// system：可选的 system 角色消息（prompt 注入防线：声明用户数据为"数据非指令"，避免 JD/简历/参考信息中的注入指令被执行）
async function callText(provider, prompt, maxTokens, onLog, signal, system) {
  if (signal && signal.aborted) return { ok: false, error: "已取消" };
  // max_tokens 超限（如视觉模型仅支持到 1024）时自动减半降级重试
  const tryOnce = (mt) => new Promise((resolve) => {
    const messages = system
      ? [{ role: "system", content: system }, { role: "user", content: prompt }]
      : [{ role: "user", content: prompt }];
    const body = JSON.stringify({
      model: provider.model,
      messages,
      max_tokens: mt,
      temperature: 0.4
    });
    let u;
    try { u = new URL(provider.baseUrl); }
    catch (e) { return resolve({ ok: false, error: "baseUrl 非法: " + provider.baseUrl }); }
    // D5 修复：原实现硬编码 https 且用 u.host（含端口）作 host，导致 http:// 协议与带端口本地端点（vLLM/Ollama 默认端口）全部失败。
    // 按协议选择 http/https，host 用 hostname、端口单独传。
    const transport = u.protocol === "http:" ? http : https;
    const req = transport.request({
      host: u.hostname,
      port: u.port || (u.protocol === "http:" ? 80 : 443),
      path: u.pathname + u.search, method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": "Bearer " + provider.apiKey,
                 "Content-Length": Buffer.byteLength(body) }
    }, res => {
      // 响应体收集用 Buffer 数组，end 时统一解码：
      // 直接 d += c 会在 chunked 传输把多字节汉字切成两块时，于块边界产生 U+FFFD 乱码（R5-乱码修复）
      const bufs = [];
      let total = 0;
      res.on("data", c => {
        bufs.push(c);
        total += c.length;
        if (total > 10 * 1024 * 1024) { req.destroy(new Error("响应超过 10MB，已中断")); }
      });
      res.on("end", () => {
        const d = Buffer.concat(bufs).toString("utf8");
        const status = res.statusCode || 0;
        if (status < 200 || status >= 300) return resolve({ ok: false, error: "HTTP " + status + ": " + d.slice(0, 300) });
        try {
          const j = JSON.parse(d);
          if (j.error) return resolve({ ok: false, error: "API error: " + JSON.stringify(j.error).slice(0, 300) });
          let content = j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
          // 部分兼容端点 content 为多模态分段数组：拼接各段文本（P3）
          if (Array.isArray(content)) content = content.map(x => (x && typeof x === "object" ? x.text : x) || "").join("");
          if (typeof content !== "string") return resolve({ ok: false, error: "响应 content 类型异常" });
          if (!content) return resolve({ ok: false, error: "响应无 content 字段" });
          resolve({ ok: true, text: content });
        } catch (e) { resolve({ ok: false, error: "响应解析失败: " + d.slice(0, 300) }); }
      });
    });
    req.setTimeout(REQUEST_TIMEOUT_MS, () => req.destroy(new Error("timeout after " + REQUEST_TIMEOUT_MS + "ms")));
    req.on("error", e => resolve({ ok: false, error: "请求错误: " + e.message }));
    // 任务取消：abort 时销毁请求（error 事件触发 resolve），完成后移除监听
    let onAbort = null;
    if (signal) {
      onAbort = () => req.destroy(new Error("cancelled"));
      if (signal.aborted) onAbort();
      else signal.addEventListener("abort", onAbort, { once: true });
      req.on("close", () => signal.removeEventListener("abort", onAbort));
    }
    req.write(body);
    req.end();
  });
  let mt = maxTokens;
  for (;;) {
    const r = await tryOnce(mt);
    if (r.ok) return r;
    if (signal && signal.aborted) return r; // 取消不触发降级重试
    if (mt > 256 && /max_tokens|max tokens/i.test(r.error)) {
      mt = Math.floor(mt / 2);
      if (onLog) onLog("max_tokens 超限，降级为 " + mt + " 重试");
      continue;
    }
    return r;
  }
}

// askText(prompt, opts) — 统一文本生成入口（内部自选 provider 链）
// opts: { cap='text', maxTokens=4096, onLog(text), signal?, onlyProvider?, system? }
//   onlyProvider：仅用指定 name 的 provider（配置页"自检"用，防自检测到别的 provider——P1-10）
//   system：system 角色消息（注入防线），透传给 callText
// 返回 Promise<string>，全部失败则 throw（含聚合错误）
async function askText(prompt, opts = {}) {
  const cap = opts.cap || "text";
  const maxTokens = opts.maxTokens || 4096;
  const onLog = opts.onLog || (() => {});
  const signal = opts.signal || null;
  const system = opts.system || null;
  const providers = availableProviders(loadConfig(), cap);
  const chain = opts.onlyProvider ? providers.filter(p => p.name === opts.onlyProvider) : providers;
  if (chain.length === 0) {
    const why = opts.onlyProvider
      ? ("provider 不可用: " + opts.onlyProvider + "（config.json 中 cap 含 " + cap + " 且 apiKey 有效的 provider）")
      : ("没有可用的 " + cap + " provider（config.json 中 cap 含 " + cap + " 且 apiKey 有效的 provider）");
    throw new Error(why);
  }
  const errors = [];
  // D1 修复：DeepSeek 等模型偶发返回空 content（思考 token 吃满 max_tokens 或瞬时故障），
  // 此前直接判失败导致单文件生成失败需人工重试。此处对「响应无 content」类错误自动重试整个 provider 链。
  // 重试次数可用环境变量 MS_AGENT_EMPTY_RETRY 调整，默认 1 次（避免无谓成本）。
  const emptyRetries = parseInt(process.env.MS_AGENT_EMPTY_RETRY || "1", 10);
  for (let attempt = 0; ; attempt++) {
    errors.length = 0;
    for (const p of chain) {
      if (signal && signal.aborted) throw new Error("任务已取消");
      // 显示名（可选增强）：配置了 displayName 时日志以「显示名 (模型名)」呈现，否则「配置名 (模型名)」
      const pLabel = p.displayName ? p.displayName + " (" + p.model + ")" : p.name + " (" + p.model + ")";
      onLog("尝试 provider: " + pLabel);
      const r = await callText(p, prompt, Math.min(maxTokens, p.maxOutputTokens || maxTokens), onLog, signal, system);
      if (signal && signal.aborted) throw new Error("任务已取消");
      if (r.ok) { onLog("成功: " + pLabel); return r.text; }
      errors.push(p.name + ": " + r.error);
      onLog(p.name + " 失败: " + r.error);
    }
    const joined = errors.join("\n  ");
    if (attempt < emptyRetries && /响应无 content/.test(joined)) {
      onLog("检测到空 content 响应（" + errors.length + " 个 provider 均失败），自动重试第 " + (attempt + 1) + " 次…");
      continue;
    }
    throw new Error("全部 provider 失败:\n  " + joined);
  }
}

// listProviders(cap) — 可用 provider 摘要（dryrun / 配置页自检用）
function listProviders(cap) {
  const all = loadConfig();
  const usable = availableProviders(all, cap || "");
  return {
    total: all.length,
    usable: usable.length,
    chain: usable.map(p => p.name + (p.model ? " (" + p.model + ")" : ""))
  };
}

module.exports = { loadConfig, availableProviders, askText, listProviders };
