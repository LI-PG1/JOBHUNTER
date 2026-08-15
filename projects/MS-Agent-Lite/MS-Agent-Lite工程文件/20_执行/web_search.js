// web_search.js — 联网搜索（可选增强，v0.4.9）
// 设计：「搜索做确定性的找，LLM 做语义的想」——本模块只负责把权威来源的标题/URL/摘要抓回来，
// 交给生成管线注入上下文，由 LLM 整合进面试材料；来源优先官方渠道（官网/官方技术博客/官方公众号/监管机构/权威媒体）。
// 当前实现 Tavily（AI 专用搜索 API，免费 1000 次/月，每次生成最多 2 次查询）；预留 provider 抽象便于后续扩展。
// 可选增强哲学：未配置 Key 时本模块不参与流程，管线自动跳过（AI 按联网核实协议标注【待联网核实】项）。
const SEARCH_ENDPOINT = "https://api.tavily.com/search";
const TIMEOUT = 25000;
const MAX_ITEMS = 6;        // 最多保留结果条数
const MAX_CONTENT = 2500;   // 每条结果正文上限（字符）
const MAX_TOTAL = 20000;    // 全部结果合并后总字符上限

// 生成搜索词：① 公司最新动态（新闻类）；② 公司+岗位技术方向（通用类）
function buildQueries(company, jdText) {
  const year = String(new Date().getFullYear());
  const kw = [];
  if (jdText) {
    const m = /([^\n。;；|]{4,24}(?:算法|开发|工程|部署|运维|架构|产品|研究|实习|Agent|模型|系统))/.exec(jdText);
    if (m) kw.push(m[1].trim());
  }
  const dyn = [company, "最新动态", "新闻", year].filter(Boolean).join(" ");
  const tech = [company, (kw[0] || "技术路线"), "产品", "发布", year].filter(Boolean).join(" ");
  return [dyn, tech];
}

function dedupe(items) {
  const seen = new Set();
  const out = [];
  for (const it of items) {
    const url = (it.url || "").split("?")[0];
    if (!url || seen.has(url)) continue;
    seen.add(url);
    out.push(it);
  }
  return out;
}

// 单次 Tavily 查询 → { ok, results:[{title,url,content}] } | { ok:false, error }
async function searchOnce(apiKey, query, signal) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT);
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  try {
    const res = await fetch(SEARCH_ENDPOINT, {
      method: "POST",
      headers: { "Authorization": "Bearer " + apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        search_depth: "basic",          // 1 积分/次（advanced 为 2）；有摘要即可喂 LLM，无需全文抓取
        max_results: 5,
        topic: "general",               // 与时间过滤组合覆盖"最新动态"
        time_range: "year",             // 只取近一年内发布/更新的来源，保证时效
        chunks_per_source: 2,           // 每条来源最多 2 段相关摘要
        include_answer: false,
        include_raw_content: false,
        include_images: false,
        safe_search: false
      }),
      signal: ctrl.signal
    });
    if (res.status === 429) throw new Error("搜索额度已用尽（Tavily 免费 1000 次/月，月初重置）或触发限流");
    if (!res.ok) throw new Error("搜索服务返回 HTTP " + res.status);
    const bufs = [];
    for await (const chunk of res.body || []) bufs.push(chunk);
    const data = JSON.parse(Buffer.concat(bufs).toString("utf8"));
    const results = Array.isArray(data.results) ? data.results : [];
    return {
      ok: true,
      results: results
        .filter(r => r && r.url)
        .map(r => ({
          title: String(r.title || "").trim(),
          url: String(r.url || "").trim(),
          content: String(r.content || "").trim().slice(0, MAX_CONTENT)
        }))
    };
  } catch (e) {
    if (signal && signal.aborted) return { ok: false, error: "已取消" };
    const msg = (e && e.name === "AbortError") ? "搜索超时（" + TIMEOUT + "ms）" : ((e && e.message) || String(e));
    return { ok: false, error: msg };
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

// webSearch(cfg, { company, jdText, signal })
//   cfg: { provider: 'tavily', apiKey }
// → { ok, items:[{title,url,content}], queries:[...] } | { ok:false, error }
async function webSearch(cfg, opts = {}) {
  if (!cfg || !cfg.apiKey) return { ok: false, error: "未配置搜索 Key（可选增强，未配置时 AI 标注【待联网核实】）" };
  const company = opts.company || "";
  if (!company) return { ok: false, error: "缺少岗位名称，无法构造搜索词" };
  const queries = buildQueries(company, opts.jdText || "");
  const merged = [];
  let firstErr = "";
  for (const q of queries) {
    if (opts.signal && opts.signal.aborted) break;
    const r = await searchOnce(cfg.apiKey, q, opts.signal);
    if (r.ok) {
      merged.push(...r.results);
      // 免费额度 1 请求/秒：两次查询之间间隔，避免 429
      if (opts.signal && !opts.signal.aborted) await new Promise(res => setTimeout(res, 1100));
    } else if (!firstErr) {
      firstErr = r.error;
    }
  }
  const items = dedupe(merged).slice(0, MAX_ITEMS);
  if (!items.length) {
    return firstErr ? { ok: false, error: firstErr } : { ok: true, items: [], queries };
  }
  // 总量封顶：超出的丢弃后半部分，防止撑爆上下文
  let total = 0;
  const kept = [];
  for (const it of items) {
    if (total + it.content.length > MAX_TOTAL) break;
    kept.push(it);
    total += it.content.length;
  }
  return { ok: true, items: kept, queries };
}

module.exports = { webSearch, buildQueries };
