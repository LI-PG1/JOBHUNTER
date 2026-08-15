// fetch_jd.js — JD URL 读取（本地插件，小任务）
// v0.4.19 增强：多级降级链 —— ① 直接 fetch（浏览器完整头，覆盖普通官网/博客）→
//                ② 站点特化 API 适配器（SPA 招聘站公开接口，如腾讯校招 join.qq.com——
//                   页面是空壳、数据由 JS 调公开 API 加载，直连/Tavily 都拿不到）→
//                ③ Tavily Extract（JS 渲染 + markdown，可穿透智联/猎聘等 JS 渲染反爬；
//                   有 webSearch Key 用 Bearer，无 Key 走 keyless 免费模式）→
//                ④ 仍失败 → 返回 { ok:false }，前端提示"请直接粘贴 JD 文本"
// 实测边界：BOSS直聘/拉勾等强验证站点（安全验证页）直连/Tavily 均无法穿透，只能提示人工粘贴；
//           智联/猎聘/公司官网 careers 页可真实抓取完整内容。
const fs = require("fs");
const path = require("path");

const DIRECT_TIMEOUT = 15000;              // 直连超时
const TAVILY_TIMEOUT = 30000;              // Tavily Extract 超时（实测含 JS 渲染，3~10s 常见）
const TAVILY_EXTRACT_ENDPOINT = "https://api.tavily.com/extract";
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

// 读取 config.json 中的 webSearch.apiKey（与 config_api.js / web_search.js 同一配置源，可选增强）
// 有 Key 时 Tavily Extract 走账号额度；无 Key 时走 keyless 免费模式（每 5 个成功 URL 计 1 积分，失败不计费）
function getTavilyKey() {
  try {
    const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf8"));
    const key = cfg && cfg.webSearch && cfg.webSearch.apiKey;
    return (typeof key === "string" && key.trim().length >= 5) ? key.trim() : "";
  } catch (e) { return ""; }
}

// 基础 SSRF 防护（P2-3）：拒绝本机/内网/链路本地地址——本地工具只应读取公网用户提供的网址
function isBlockedHost(hostname) {
  if (!hostname) return true;
  const h = String(hostname).toLowerCase();
  if (h === "localhost" || h.endsWith(".localhost")) return true;
  if (h === "::1" || h.startsWith("::ffff:")) {
    const v4 = h.startsWith("::ffff:") ? h.slice(7) : null;
    return v4 ? isBlockedHost(v4) : true;
  }
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
  if (m) {
    const a = +m[1], b = +m[2], c = +m[3], d = +m[4];
    if (a === 0 || a === 127 || a >= 224) return true;   // 0.x / loopback / multicast / reserved
    if (a === 10) return true;                            // 10/8
    if (a === 169 && b === 254) return true;              // 169.254/16（含云 metadata）
    if (a === 172 && b >= 16 && b <= 31) return true;     // 172.16/12
    if (a === 192 && b === 168) return true;              // 192.168/16
    return false;
  }
  return false; // 公网域名放行（最终跳转 IP 无法在纯 Node 层完全防御，见评估报告备注）
}

// ① 直接 fetch：浏览器完整头（UA + Accept-Language + Accept-Encoding + Referer + Sec-Fetch 系列），
//    undici 自动解压 gzip/br，提升普通站点成功率（v0.4.19 增强）
async function fetchOnce(url, timeout, signal) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  // 合并外部取消信号（P1-3）：任务取消时立即中断本次抓取
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Referer": "https://www.google.com/"
      },
      redirect: "follow",
      signal: ctrl.signal
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    // 非文本类型拒绝（P2-2）：只读网页文本，图片/压缩包/二进制一律判失败，避免把二进制当文本提取
    if (!ct.includes("text/") && !ct.includes("html") && !ct.includes("json")) {
      throw new Error("页面类型不是文本（Content-Type: " + (ct || "未知") + "）");
    }
    // 响应体大小上限（2MB）：防超大页面拖垮内存（P2-1）
    if (Number(res.headers.get("content-length") || 0) > 2 * 1024 * 1024) throw new Error("页面过大（>2MB）");
    // 响应体收集用 Buffer 数组，读取完成后统一解码：直接 raw += chunk 会在分块传输把多字节汉字切成两块时产生 U+FFFD 乱码（R5-乱码修复）
    const bufs = [];
    let total = 0;
    for await (const chunk of res.body || []) {
      bufs.push(chunk);
      total += chunk.length;
      if (total > 2 * 1024 * 1024) { ctrl.abort(); throw new Error("页面过大（>2MB），已中断读取"); }
    }
    const raw = Buffer.concat(bufs).toString("utf8");
    // 提取正文文本：优先按常见标记粗筛，去标签去空白
    let text = raw;
    if (ct.includes("html")) {
      text = raw
        .replace(/<script[\s\S]*?<\/script>/gi, " ")
        .replace(/<style[\s\S]*?<\/style>/gi, " ")
        .replace(/<[^>]+>/g, " ")
        .replace(/&nbsp;/gi, " ")
        .replace(/&amp;/gi, "&")
        .replace(/&lt;/gi, "<")
        .replace(/&gt;/gi, ">")
        .replace(/&quot;/gi, '"')
        .replace(/&#\d+;/g, " ")
        .replace(/\s+/g, " ")
        .trim();
    }
    if (!text || text.length < 20) throw new Error("页面无有效文本（网站可能限制程序读取）");
    // 反爬验证页检测（v0.4.19）：BOSS直聘等站对数据中心/无头请求返回「安全验证」挑战页，
    // 其短文本（实测 76 字）能通过上面的 20 字下限，必须识别并判失败，避免把验证页当 JD 喂给 LLM
    if (text.length < 500 && /安全验证|人机验证|请完成以下验证|滑动验证|Just a moment|Checking your browser|Access Denied|access denied|captcha|challenge/i.test(text)) {
      throw new Error("页面为反爬验证页，无法读取正文（" + text.slice(0, 30).replace(/\s+/g, " ") + "…）");
    }
    return { ok: true, text, from: res.url || url };
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

// ② 站点特化 API 适配器（v0.4.19）：SPA 招聘站页面是空壳，岗位数据由 JS 调公开 API 加载——
//    直连/Tavily 都拿不到，但站点公开接口可直接取数。表驱动，新增站点只需加一条适配器。
async function tencentJoinAdapter(u, signal) {
  const postid = u.searchParams.get("postid");
  if (!postid) return null;   // URL 无岗位 ID → 不适用，交给下一级
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), DIRECT_TIMEOUT);
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  try {
    const res = await fetch("https://join.qq.com/api/v1/jobDetails/getJobDetailsByPostId?postId=" + encodeURIComponent(postid), {
      headers: {
        "User-Agent": UA,
        "Referer": "https://join.qq.com/post_detail.html?postid=" + encodeURIComponent(postid),
        "Accept": "application/json, text/plain, */*"
      },
      signal: ctrl.signal
    });
    if (!res.ok) return null;
    const data = await res.json();
    const d = data && data.status === 0 ? data.data : null;
    if (!d || !d.title) return null;
    const parts = [];
    parts.push("岗位：" + d.title);
    if (d.tidName) parts.push("类别：" + d.tidName);
    if (d.workCityList && d.workCityList.length) parts.push("工作地点：" + d.workCityList.join("/"));
    if (d.recruitCityList && d.recruitCityList.length) parts.push("面试方式：" + d.recruitCityList.join("/"));
    if (d.desc) parts.push("\n【岗位职责】\n" + String(d.desc).trim());
    if (d.request) parts.push("\n【任职要求】\n" + String(d.request).trim());
    if (d.intentionBGDList && d.intentionBGDList.length) {
      const depts = d.intentionBGDList.map(b => {
        const sub = (b.departmentList || []).map(x => x.name).join("、");
        return b.showTxt + (sub ? "（" + sub + "）" : "");
      });
      parts.push("\n【招聘部门】\n" + depts.join("\n"));
    }
    const text = parts.join("\n").trim();
    if (text.length < 20) return null;
    return { ok: true, text, from: "腾讯校招岗位接口" };
  } catch (e) {
    return null;   // 适配器失败 → 交给下一级（Tavily）
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

// 适配器注册表：match 命中才尝试 fetch；fetch 返回 null = 不适用/失败（交给下一级）
const SITE_ADAPTERS = [
  { name: "腾讯校招", match: u => u.hostname === "join.qq.com" && /^\/post_detail\.html/.test(u.pathname), fetch: tencentJoinAdapter },
];

async function tryAdapters(u, signal) {
  for (const a of SITE_ADAPTERS) {
    if (!a.match(u)) continue;
    const r = await a.fetch(u, signal);
    if (r) return r;
  }
  return null;
}

// ③ Tavily Extract：服务端无头浏览器抓取 + markdown，可拿到 JS 渲染后的真实内容，
//    对直连被反爬/验证拦截的站点（智联/猎聘等）有穿透能力（v0.4.19 新增）
async function tavilyExtract(url, signal) {
  const key = getTavilyKey();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TAVILY_TIMEOUT);
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  try {
    const headers = { "Content-Type": "application/json" };
    if (key) headers["Authorization"] = "Bearer " + key;
    else headers["X-Tavily-Access-Mode"] = "keyless";   // 无 Key 也走免费 keyless 模式（零配置）
    const res = await fetch(TAVILY_EXTRACT_ENDPOINT, {
      method: "POST",
      headers,
      signal: ctrl.signal,
      body: JSON.stringify({ urls: [url], format: "markdown", extract_depth: "basic" })
    });
    if (res.status === 429) throw new Error("Tavily 额度已用尽（每月免费 1000 积分，月初重置）或触发限流");
    if (!res.ok) throw new Error("Tavily 抓取服务返回 HTTP " + res.status);
    const data = await res.json();
    const item = data && Array.isArray(data.results) && data.results[0];
    const text = item && item.raw_content ? String(item.raw_content).trim() : "";
    if (!text || text.length < 20) {
      // failed_results 里带站点侧原因（如"Error fetching content"），直接透出便于定位
      const fail = data && Array.isArray(data.failed_results) && data.failed_results[0] && data.failed_results[0].error;
      throw new Error(fail ? "Tavily 无法抓取该网站（" + fail + "）" : "Tavily 返回内容为空");
    }
    return { ok: true, text, from: url + "（经 Tavily 智能抓取）" };
  } catch (e) {
    if (signal && signal.aborted) return { ok: false, error: "已取消" };
    const msg = e && e.name === "AbortError" ? "Tavily 抓取超时（30s）" : ((e && e.message) || String(e));
    return { ok: false, error: msg };
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

// fetchJD(url, signal?) → Promise<{ ok, text?, error?, from? }>
// 多级降级链：① 直接 fetch（重试 1 次）→ ② 站点适配器 → ③ Tavily Extract → ④ 失败提示
async function fetchJD(url, signal) {
  let u;
  try { u = new URL(url); } catch (e) { return { ok: false, error: "URL 格式非法" }; }
  if (u.protocol !== "http:" && u.protocol !== "https:") return { ok: false, error: "仅支持 http/https 链接" };
  // SSRF 防护（P2-3）：拒绝本机/内网/链路本地地址（本地工具只读公网用户提供的网址）
  if (isBlockedHost(u.hostname)) return { ok: false, error: "该链接指向本机/内网地址，已拒绝读取（仅支持公网网址）" };
  if (signal && signal.aborted) return { ok: false, error: "已取消" };

  // ① 直接 fetch（网络抖动重试 1 次）
  let directErr = "";
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await fetchOnce(u.href, DIRECT_TIMEOUT, signal);
    } catch (e) {
      if (signal && signal.aborted) return { ok: false, error: "已取消" };
      directErr = e && e.name === "AbortError" ? "读取超时（15s）" : ((e && e.message) || String(e));
    }
  }

  // ② 站点特化 API 适配器（SPA 招聘站公开接口，如腾讯校招）
  const adapted = await tryAdapters(u, signal);
  if (adapted) return adapted;
  if (signal && signal.aborted) return { ok: false, error: "已取消" };

  // ③ Tavily Extract（JS 渲染 + markdown，穿透部分 JS 渲染反爬）
  const tv = await tavilyExtract(u.href, signal);
  if (tv.ok) return tv;
  if (signal && signal.aborted) return { ok: false, error: "已取消" };

  // ④ 仍失败：给出分级原因 + 建议（BOSS直聘等强验证站只能人工粘贴）
  return {
    ok: false,
    error: "信息读取失败：直接读取（" + directErr + "），Tavily 智能抓取（" + tv.error + "）。"
      + "该网站可能设置了强反爬或需人工验证（如 BOSS直聘 的安全验证页），建议直接粘贴 JD 文本（更准确）。"
  };
}

module.exports = { fetchJD, tavilyExtract };
