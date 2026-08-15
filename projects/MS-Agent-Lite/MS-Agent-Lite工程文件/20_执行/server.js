// server.js — 应用服务（原静态预览升级版）
//   - 静态托管 20_执行/web/（任务式面板）+ 20_执行 下其他文件
//   - API：任务创建/状态/SSE/取消/重试、JD 抓取、简历解析、provider 管理、搜索分区
//   - 预览：/preview/<公司>/<文件> → 30_产出/面试材料/<公司>/
// 用法：node 20_执行\server.js   →  http://127.0.0.1:8900
const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { runGenerate, retryFile, runBuild, runVerify, runCheck, collectVerifyItems } = require("./pipeline.js");
const { parseResumeFromBuffer } = require("./parse_resume.js");
const { fetchJD } = require("./fetch_jd.js");
const configApi = require("./config_api.js");
const { ZONES } = require("./search_zones.js");
const cliTools = require("./cli_tools.js");
const visionAnalyze = require("./vision_analyze.js");

const TOOLS = __dirname;
const ROOT = path.resolve(TOOLS, "..");
const MATERIALS = path.join(ROOT, "30_产出", "面试材料");
const port = 8900;

// ================= 任务存储 =================
const tasks = new Map(); // taskId -> { state, events:[], clients:Set, files:Map, result, input }
const companyLocks = new Map(); // company -> taskId：同岗位并发互斥（防两任务互踩产物目录）

// ===== 任务持久化（D4 修复）：服务重启 / 进程退出后任务不丢失，taskId 仍可用（状态/日志/重试）=====
const STORE_PATH = path.join(TOOLS, "_task_store.json");
const STORE_TTL_MS = 24 * 60 * 60 * 1000; // 磁盘保留：终态任务最多保留 24 小时，启动时清理超期记录
let _storeTimer = null;
function saveStore() {
  // 防抖落盘：SSE 事件密集时合并写，终态/创建后都会触发
  if (_storeTimer) return;
  _storeTimer = setTimeout(() => {
    _storeTimer = null;
    try {
      const data = {};
      for (const [id, t] of tasks) {
        data[id] = { state: t.state, events: t.events, files: [...t.files.entries()], result: t.result, input: t.input, terminalAt: t.terminalAt || null };
      }
      fs.writeFileSync(STORE_PATH, JSON.stringify(data));
    } catch (e) { console.error("[store] 保存任务状态失败:", e && e.message); }
  }, 300);
}
function loadStore() {
  try {
    if (!fs.existsSync(STORE_PATH)) return;
    const data = JSON.parse(fs.readFileSync(STORE_PATH, "utf8"));
    const now = Date.now();
    for (const [id, rec] of Object.entries(data || {})) {
      if (!rec || typeof rec !== "object" || !/^[0-9a-f]+$/.test(id)) continue;
      // 磁盘清理：终态任务超 24 小时不再恢复
      if (rec.terminalAt && now - rec.terminalAt > STORE_TTL_MS) continue;
      const t = {
        state: rec.state || "error",
        events: Array.isArray(rec.events) ? rec.events : [],
        files: new Map(Array.isArray(rec.files) ? rec.files : []),
        result: rec.result || null,
        input: rec.input || null,
        clients: new Set(), controller: null, ttlTimer: null, terminalAt: rec.terminalAt || null
      };
      // 服务重启时原进程内的生成流程已丢失：非终态任务统一置为 error，
      // 避免「卡在运行中」假象；日志与文件列表保留，仍可对失败文件重试
      if (!["done", "error", "cancelled"].includes(t.state)) {
        t.state = "error";
        t.terminalAt = Date.now();
        t.events.push({ type: "error", text: "服务已重启，原生成任务中断，请对失败文件重试或重新生成" });
        t.result = { type: "error", text: "服务已重启，原生成任务中断，请对失败文件重试或重新生成" };
      }
      tasks.set(id, t);
    }
    // 同步清理磁盘上的过期记录
    saveStore();
    if (tasks.size) console.log("[store] 已恢复 " + tasks.size + " 个历史任务");
  } catch (e) { console.error("[store] 恢复任务状态失败:", e && e.message); }
}

// 进程级兜底：畸形输入 / 客户端断连等异步异常不退出进程（P0-1 / P0-3 防线）
process.on("uncaughtException", e => console.error("[uncaughtException]", e && e.message));
process.on("unhandledRejection", e => console.error("[unhandledRejection]", e && (e && e.message || e)));

function pushEvent(taskId, evt) {
  const t = tasks.get(taskId);
  if (!t) return;
  t.events.push(evt);
  // 维护快照
  if (evt.type === "step") {
    // cancelled 为终态，后续 step 事件不得再改写状态（P1-5/P1-9 状态守卫）
    if (t.state !== "cancelled") t.state = (evt.status === "running") ? evt.name : (evt.status === "done" ? evt.name + "-done" : evt.name + "-" + evt.status);
  }
  if (evt.type === "file") t.files.set(evt.name, { status: evt.status, bytes: evt.bytes, error: evt.error });
  if (evt.type === "done") { t.state = "done"; t.result = evt; }
  if (evt.type === "error") { t.state = "error"; t.result = evt; }
  // 广播 SSE
  const data = "event: " + evt.type + "\ndata: " + JSON.stringify(evt) + "\n\n";
  for (const client of t.clients) {
    try { client.res.write(data); } catch (e) { /* ignore */ }
  }
  // 终态：清理 SSE 连接 + 任务 TTL（30 分钟，防 tasks Map 长期运行内存增长）
  // 只认 done/error/cancelled 为终态；building/verifying 等步骤级 failed 不是终态（P1-9）
  if (evt.type === "done" || evt.type === "error" || (evt.type === "step" && evt.status === "cancelled")) {
    for (const client of t.clients) { try { client.res.end(); } catch (e) {} }
    t.clients.clear();
    t.terminalAt = Date.now(); // 持久化记录终态时间，供启动时磁盘清理（D4）
    // 释放同岗位并发锁（P1-4）
    if (t.input && companyLocks.get(t.input.company) === taskId) companyLocks.delete(t.input.company);
    // 内存 TTL 到期删除；磁盘记录保留（_task_store.json），重启后仍可重试（D4 修复）
    if (!t.ttlTimer) t.ttlTimer = setTimeout(() => { tasks.delete(taskId); saveStore(); }, 30 * 60 * 1000);
  }
  // 任务状态变化落盘（防抖）：重启后可恢复任务、日志与重试数据（D4 修复）
  saveStore();
}

// ================= 工具函数 =================
function sendJson(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    // 请求体收集用 Buffer 数组，end 时统一解码：直接 d += c 会在分块传输把多字节汉字切成两块时产生 U+FFFD 乱码（R5-乱码修复）
    const bufs = [];
    let total = 0;
    req.on("data", c => { bufs.push(c); total += c.length; if (total > 64 * 1024 * 1024) { reject(new Error("body 过大")); req.destroy(); } });
    req.on("end", () => resolve(Buffer.concat(bufs).toString("utf8")));
    req.on("error", reject);
  });
}
function parseDataUrl(dataUrl) {
  // "data:<mime>;base64,<b64>"
  const m = /^data:([^;,]+)(;[^,]*)?,(.*)$/s.exec(dataUrl || "");
  if (!m) return null;
  return { mime: m[1], base64: m[3] };
}
function mimeToExt(mime) {
  const map = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "text/plain": "txt",
    "text/markdown": "md"
  };
  return map[mime] || null;
}
// 图片 mime → 扩展名（OCR 端点用；与 mimeToExt 分离，避免简历上传误收图片）
function imgMimeToExt(mime) {
  const map = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/bmp": "bmp",
    "image/gif": "gif"
  };
  return map[mime] || null;
}

// ================= 路由处理 =================
async function handleApi(req, res, url) {
  const p = url.pathname;

  // 跨站防护（P1-1）：浏览器发出的跨站请求必带 Origin/Referer，非本机来源一律拒绝；
  // curl 等本机调用不带这些头，正常放行
  if (req.method !== "GET") {
    const origin = req.headers.origin || req.headers.referer || "";
    if (origin && !/^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?($|\/)/i.test(origin)) {
      return sendJson(res, 403, { error: "拒绝来自其他网站的请求" });
    }
    const ct = req.headers["content-type"] || "";
    if (ct && !ct.includes("application/json")) {
      return sendJson(res, 415, { error: "Content-Type 必须为 application/json" });
    }
  }

  // ---- provider 管理 ----
  if (p === "/api/providers" && req.method === "GET") {
    try { return sendJson(res, 200, { providers: configApi.getProviders() }); }
    catch (e) { return sendJson(res, 500, { error: e.message }); }
  }
  if (p === "/api/providers" && req.method === "POST") {
    try { return sendJson(res, 200, { providers: configApi.saveProvider(JSON.parse(await readBody(req))) }); }
    catch (e) { return sendJson(res, 400, { error: e.message }); }
  }
  const provDel = /^\/api\/providers\/([^/]+)$/.exec(p);
  if (provDel && req.method === "DELETE") {
    try { return sendJson(res, 200, { providers: configApi.deleteProvider(decodeURIComponent(provDel[1])) }); }
    catch (e) { return sendJson(res, 400, { error: e.message }); }
  }
  const provTest = /^\/api\/providers\/([^/]+)\/test$/.exec(p);
  if (provTest && req.method === "POST") {
    try {
      const body = JSON.parse(await readBody(req));
      const r = await configApi.testProvider(decodeURIComponent(provTest[1]), { real: !!body.real });
      return sendJson(res, 200, r);
    } catch (e) { return sendJson(res, 400, { ok: false, error: e.message }); }
  }

  // ---- 公司列表 ----
  if (p === "/api/companies" && req.method === "GET") {
    // 逐条容错（P2-10）：单个异常条目不影响其他结果
    let list = [];
    try {
      list = fs.readdirSync(MATERIALS).filter(x => {
        try {
          const full = path.join(MATERIALS, x);
          // 产物重命名容错（R12）：目录内存在任意 .html（重命名后的结果页也算），即视为有效岗位目录
          return fs.statSync(full).isDirectory() && fs.readdirSync(full).some(f => /\.html$/i.test(f));
        } catch (e) { return false; }
      });
    } catch (e) {}
    return sendJson(res, 200, { companies: list });
  }

  // ---- 行业预设搜索分区 ----
  if (p === "/api/search-zones" && req.method === "GET") {
    return sendJson(res, 200, { zones: ZONES });
  }

  // ---- 本地 CLI 工具探测（P0 适配层：markitdown/mineru/rapidocr 等可选增强） ----
  if (p === "/api/cli-tools" && req.method === "GET") {
    try {
      const tools = await cliTools.probeAll();
      return sendJson(res, 200, { tools });
    } catch (e) { return sendJson(res, 500, { error: e.message }); }
  }

  // ---- 内置 OCR 引擎状态（开箱即用：onnxruntime-node + PP-OCRv4 轻量模型） ----
  if (p === "/api/ocr-engine" && req.method === "GET") {
    try {
      const engine = require("./ocr_js.js").checkEngine();
      return sendJson(res, 200, { engine });
    } catch (e) { return sendJson(res, 500, { error: e.message }); }
  }

  // ---- 联网搜索配置（v0.4.9，可选增强：Tavily Key，AI 遇时效信息自动联网核实） ----
  if (p === "/api/web-search") {
    if (req.method === "GET") {
      try { return sendJson(res, 200, configApi.getWebSearchStatus()); }
      catch (e) { return sendJson(res, 500, { error: e.message }); }
    }
    if (req.method === "POST") {
      try {
        const body = JSON.parse(await readBody(req));
        // provider 白名单（v0.4.9 代码审查修复）：当前仅支持 tavily，防任意值落盘
        const provider = (body && body.provider) || "tavily";
        if (provider !== "tavily") return sendJson(res, 400, { error: "不支持的搜索服务：仅支持 tavily" });
        return sendJson(res, 200, configApi.saveWebSearch({ apiKey: body && body.apiKey, provider }));
      } catch (e) { return sendJson(res, 400, { error: e.message }); }
    }
  }

  // ---- 图片 OCR（三级回退：内置引擎 > CLI OCR > vision provider，均可选增强） ----
  if (p === "/api/ocr" && req.method === "POST") {
    try {
      const body = JSON.parse(await readBody(req));
      const du = parseDataUrl(body.imageDataUrl);
      if (!du || !du.base64) return sendJson(res, 400, { ok: false, error: "图片数据无效（需 data URL，如 data:image/png;base64,...）" });
      const ext = imgMimeToExt(du.mime);
      if (!ext) return sendJson(res, 400, { ok: false, error: "不支持的图片格式（支持 png / jpg / webp / bmp / gif）" });
      // 写临时文件后交给 vision_analyze 三级回退，完成后清理
      const tmp = path.join(require("os").tmpdir(), "msa-ocr-" + Date.now() + "-" + Math.floor(Math.random() * 1e6) + "." + ext);
      fs.writeFileSync(tmp, Buffer.from(du.base64, "base64"));
      try {
        const r = await visionAnalyze.extractText(tmp);
        return sendJson(res, r.ok ? 200 : 422, r);
      } finally {
        try { fs.unlinkSync(tmp); } catch (e) { /* 清理失败不影响结果 */ }
      }
    } catch (e) { return sendJson(res, 400, { ok: false, error: e.message }); }
  }

  // ---- JD URL 抓取 ----
  if (p === "/api/fetch-jd" && req.method === "POST") {
    try {
      const body = JSON.parse(await readBody(req));
      if (!body.url) return sendJson(res, 400, { ok: false, error: "缺少 url" });
      const r = await fetchJD(body.url);
      return sendJson(res, r.ok ? 200 : 422, r);
    } catch (e) { return sendJson(res, 400, { ok: false, error: e.message }); }
  }

  // ---- 简历解析预览（上传后立即解析并返回文本） ----
  if (p === "/api/parse-resume" && req.method === "POST") {
    try {
      const body = JSON.parse(await readBody(req));
      const du = parseDataUrl(body.resumeFile);
      let ext = body.resumeExt || (du && mimeToExt(du.mime));
      if (!du || !ext) return sendJson(res, 400, { ok: false, error: "简历文件格式无法识别（支持 pdf/docx/txt/md）" });
      const r = await parseResumeFromBuffer(Buffer.from(du.base64, "base64"), ext);
      return sendJson(res, 200, r);
    } catch (e) { return sendJson(res, 400, { ok: false, error: e.message }); }
  }

  // ---- 创建生成任务 ----
  if (p === "/api/material" && req.method === "POST") {
    let body;
    try { body = JSON.parse(await readBody(req)); }
    catch (e) { return sendJson(res, 400, { error: "请求体不是合法 JSON" }); }
    const company = (body.company || "").trim();
    if (!company) return sendJson(res, 400, { error: "company 必填（岗位名称，生成 <岗位名称>面试准备.html）" });
    // 岗位名称用于创建目录与文件名，禁止路径分隔符/非法字符/纯点段，防路径注入（P0-2）
    if (!/^(?!\.{1,2}$)[^\\\/:*?"<>|\u0000-\u001f]{1,80}$/.test(company)) {
      return sendJson(res, 400, { error: "company 含非法字符（不能包含 \\ / : * ? \" < > | 或控制字符，也不能是 . / ..）" });
    }
    if (!body.jdText && !body.jdUrl) return sendJson(res, 400, { error: "jdText / jdUrl 至少提供一个" });
    // 超长文本不拒绝、由流水线统一截断（buildSharedCtx trimText 上限 20000 字并标注"完整内容见 _上下文快照.md"），与前端提示一致
    if (body.resumeText && body.resumeText.length > 20000) return sendJson(res, 400, { error: "resumeText 过长（上限 20000 字）" });
    if (!body.resumeFile) return sendJson(res, 400, { error: "请上传简历" });
    if (Array.isArray(body.urls) && body.urls.length > 15) return sendJson(res, 400, { error: "参考网址最多 15 条" }); // P2-3 条数上限（与流水线 MAX_URL_COUNT=15 一致）

    const taskId = crypto.randomBytes(6).toString("hex");
    // 同岗位并发互斥（P1-4）：避免两个任务互踩产物目录
    if (companyLocks.has(company)) {
      return sendJson(res, 409, { error: "「" + company + "」正在生成中，请等当前任务完成或先取消后再试" });
    }
    companyLocks.set(company, taskId);
    const controller = new AbortController();
    const task = { state: "pending", events: [], clients: new Set(), files: new Map(), result: null, input: body, controller, ttlTimer: null };
    tasks.set(taskId, task);
    saveStore(); // 创建即落盘：任务还没收到任何事件前就重启，也能在恢复后看到该任务（D4）
    pushEvent(taskId, { type: "step", name: "pending", status: "running" });

    // 后台执行
    (async () => {
      let resumeText = body.resumeText || "";
      let jdText = body.jdText || "";
      try {
        // 1) 上传简历解析
        if (body.resumeFile) {
          pushEvent(taskId, { type: "step", name: "parsing", status: "running" });
          const du = parseDataUrl(body.resumeFile);
          let ext = body.resumeExt || (du && mimeToExt(du.mime));
          if (!du || !ext) throw new Error("简历文件格式无法识别（支持 pdf/docx/txt/md）");
          const buffer = Buffer.from(du.base64, "base64");
          const r = await parseResumeFromBuffer(buffer, ext);
          resumeText = r.text;
          // 回写任务 input：retry 时直接复用，避免上传文件场景重试丢失简历文本
          body.resumeText = resumeText;
          pushEvent(taskId, { type: "log", text: "解析上传简历：" + ext + "，约 " + r.meta.lines + " 行" });
          pushEvent(taskId, { type: "step", name: "parsing", status: "done", detail: r.meta.lines + " 行" });
        }
        // 2) JD URL 抓取
        if (!jdText && body.jdUrl) {
          pushEvent(taskId, { type: "step", name: "fetching", status: "running" });
          const r = await fetchJD(body.jdUrl, controller.signal);
          if (!r.ok) throw new Error(r.error);
          jdText = r.text;
          // 回写任务 input：retry 时直接复用抓取结果，避免重复请求且丢失 JD
          body.jdText = jdText;
          pushEvent(taskId, { type: "log", text: "JD 抓取成功（" + r.from + "），文本 " + r.text.length + " 字符" });
          pushEvent(taskId, { type: "step", name: "fetching", status: "done" });
        }
        // 3) 补充参考网址抓取（逐条尽力，失败不阻断）
        const urls = [];
        const rawUrls = Array.isArray(body.urls) ? body.urls : [];
        if (rawUrls.length) {
          pushEvent(taskId, { type: "step", name: "fetching", status: "running" });
          for (let i = 0; i < rawUrls.length; i++) {
            if (controller.signal.aborted) { pushEvent(taskId, { type: "log", text: "已取消，停止抓取参考网址" }); break; } // P1-3：取消即时生效
            const u = rawUrls[i];
            const url = (typeof u === "string" ? u : (u && u.url)) || "";
            if (!url) continue;
            if (u && u.text) { urls.push({ url, text: u.text }); continue; } // 前端已抓好的文本直接用
            pushEvent(taskId, { type: "log", text: "抓取参考网址 " + (i + 1) + "/" + rawUrls.length + ": " + url.slice(0, 80) });
            try {
              const r = await fetchJD(url, controller.signal);
              if (r.ok) urls.push({ url, text: r.text });
              else pushEvent(taskId, { type: "log", text: "参考网址抓取失败（跳过）: " + (r.error || "") });
            } catch (e) {
              pushEvent(taskId, { type: "log", text: "参考网址抓取异常（跳过）: " + (e.message || "") });
            }
          }
          pushEvent(taskId, { type: "log", text: "参考网址抓取完成：成功 " + urls.length + "/" + rawUrls.length });
          pushEvent(taskId, { type: "step", name: "fetching", status: "done" });
        }
        // 4) 生成管线
        // 用独立对象传参并在结束后回写 searchInfo 到任务 input：retry 时直接复用联网搜索资料
        const genInput = { company, resumeVer: body.resumeVer || "", resumeText, jdText, urls, refInfo: body.refInfo || "" };
        await runGenerate(genInput, {
          onProgress: evt => pushEvent(taskId, evt),
          signal: controller.signal
        });
        if (genInput.searchInfo) body.searchInfo = genInput.searchInfo;
      } catch (e) {
        if (controller.signal.aborted) return; // 取消后的异常不覆盖 cancelled 状态（P1-5）
        pushEvent(taskId, { type: "error", text: e.message });
      }
    })();

    return sendJson(res, 200, { taskId });
  }

  // ---- 任务状态 / SSE / 取消 / 重试 ----
  const taskMatch = /^\/api\/task\/([0-9a-f]+)$/.exec(p);
  if (taskMatch) {
    const t = tasks.get(taskMatch[1]);
    if (!t) return sendJson(res, 404, { error: "task 不存在" });
    if (req.method === "GET") {
      return sendJson(res, 200, { taskId: taskMatch[1], state: t.state,
        files: [...t.files.entries()].map(([name, f]) => ({ name, ...f })),
        result: t.result, log: t.events.filter(e => e.type === "log").map(e => e.text) });
    }
  }
  const sseMatch = /^\/api\/task\/([0-9a-f]+)\/events$/.exec(p);
  if (sseMatch && req.method === "GET") {
    const t = tasks.get(sseMatch[1]);
    if (!t) return sendJson(res, 404, { error: "task 不存在" });
    res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no" });
    res.write("retry: 2000\n\n");
    // 重放历史事件
    for (const evt of t.events) res.write("event: " + evt.type + "\ndata: " + JSON.stringify(evt) + "\n\n");
    const client = { res };
    t.clients.add(client);
    req.on("close", () => t.clients.delete(client));
    // 若任务已终态且没有 done/error 被重放后关闭
    if (/done|error/.test(t.state) || /cancelled|failed$/.test(t.state)) { try { res.end(); } catch (e) {} t.clients.delete(client); }
    return;
  }
  const cancelMatch = /^\/api\/task\/([0-9a-f]+)\/cancel$/.exec(p);
  if (cancelMatch && req.method === "POST") {
    const t = tasks.get(cancelMatch[1]);
    if (!t) return sendJson(res, 404, { error: "task 不存在" });
    if (t.state && /done|error|cancelled|failed$/.test(t.state)) {
      return sendJson(res, 409, { error: "任务已结束，无法取消" }); // P1-9：终态不可回退
    }
    if (t.controller) t.controller.abort();
    pushEvent(cancelMatch[1], { type: "step", name: "cancelled", status: "cancelled" });
    return sendJson(res, 200, { ok: true });
  }
  const retryMatch = /^\/api\/task\/([0-9a-f]+)\/retry-file$/.exec(p);
  if (retryMatch && req.method === "POST") {
    const t = tasks.get(retryMatch[1]);
    if (!t) return sendJson(res, 404, { error: "task 不存在" });
    try {
      const body = JSON.parse(await readBody(req));
      const input = t.input;
      if (!input || !input.company) return sendJson(res, 400, { ok: false, error: "任务数据不完整" });
      // 同岗位并发互斥（P1-4）：retry 期间其他任务不得并发写同目录
      if (companyLocks.has(input.company) && companyLocks.get(input.company) !== retryMatch[1]) {
        return sendJson(res, 409, { ok: false, error: "「" + input.company + "」正在生成中，请稍后再试" });
      }
      companyLocks.set(input.company, retryMatch[1]);
      try {
      // retry 的可取消信号：原 controller 可能在"取消"时已被 abort（AbortController 不可逆），
      // 直接透传已终止的 signal 会导致重试立即失败——此时重建可重试的 controller（审查发现取消后 retry 必失败）
      let retrySignal = t.controller && !t.controller.signal.aborted ? t.controller.signal : null;
      if (!retrySignal) {
        t.controller = new AbortController();
        retrySignal = t.controller.signal;
      }
      const r = await retryFile({ company: input.company, resumeVer: input.resumeVer || "", resumeText: input.resumeText || "", jdText: input.jdText || "", urls: input.urls || [], refInfo: input.refInfo || "", searchInfo: input.searchInfo || "" }, body.name, {
        onProgress: evt => pushEvent(retryMatch[1], evt),
        signal: retrySignal
      });
      if (!r.ok) return sendJson(res, 200, r);
      // 重试成功 → 补跑 build + verify + check，确保 HTML 产物与审核随之更新（否则产物仍是旧的）
      const ver = (input.resumeVer || "").toUpperCase();
      const outDir = path.join(MATERIALS, input.company);
      pushEvent(retryMatch[1], { type: "log", text: "重试成功，正在重新构建 HTML…" });
      let build = null, verify = null;
      try { const out = await runBuild(input.company, ver); build = { ok: true, stdout: out.trim() }; }
      catch (e) { build = { ok: false, stdout: ((e && (e.stdout || e.message)) || String(e)).trim() }; }
      pushEvent(retryMatch[1], { type: "build", ok: build.ok, detail: build.stdout });
      try { const out = await runVerify(input.company); verify = { ok: true, output: out.trim() }; }
      catch (e) { verify = { ok: false, output: ((e && (e.stdout || e.message)) || String(e)).trim() }; }
      pushEvent(retryMatch[1], { type: "verify", ok: verify.ok, detail: verify.output });
      let check = null;
      try {
        const cardPath = path.join(ROOT, "10_知识库", "简历基准", "参与边界卡.md");
        const card = fs.existsSync(cardPath) ? fs.readFileSync(cardPath, "utf8") : "";
        const c = await runCheck(outDir, card, input.resumeText || "", ver, evt => pushEvent(retryMatch[1], evt));
        check = { ok: c.ok, output: c.output };
        pushEvent(retryMatch[1], { type: "check", ok: c.ok, output: c.output });
      } catch (e) {
        check = { ok: null, output: (e && e.message) || String(e) };
        pushEvent(retryMatch[1], { type: "log", text: "内容审核跳过（" + check.output.slice(0, 120) + "）" });
      }
      pushEvent(retryMatch[1], { type: "log",
        text: "重试完成：build " + (build.ok ? "✓" : "✗") + " / verify " + (verify.ok ? "✓" : "✗") +
          (check ? " / 审核 " + (check.ok === true ? "PASS" : check.ok === false ? "WARN" : "跳过") : "") });
      // 重跑【待联网核实】清单（v0.4.9 代码审查修复）：重试文件可能新增/清除标记，推送更新事件供前端重绘
      const needsVerify = collectVerifyItems(outDir);
      pushEvent(retryMatch[1], { type: "needs-verify", needsVerify });
      return sendJson(res, 200, { ok: true, build: build.ok, verify: verify.ok, check: check && check.ok, needsVerify });
      } finally {
        // 释放同岗位锁（P1-4）
        if (companyLocks.get(input.company) === retryMatch[1]) companyLocks.delete(input.company);
      }
    } catch (e) { return sendJson(res, 400, { ok: false, error: e.message }); }
  }

  // D4 修复：未匹配的 API 路径返回中文 404，不再输出英文 "Not Found"
  return sendJson(res, 404, { error: "接口不存在：" + p });
}

// ================= 静态 + 预览 =================
function serveStatic(res, filePath) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      // D4 修复：404 不再输出英文 "Not Found"——结果页缺失时给出中文指引页（预览 iframe 内可见），其余文件返回中文 JSON
      if (/\.html$/i.test(filePath)) {
        const body = '<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8"><title>文件不存在</title></head>' +
          '<body style="font-family:system-ui,Segoe UI,Microsoft YaHei,sans-serif;background:#f9fafb;color:#1f2937;padding:48px 24px;text-align:center">' +
          '<h2 style="font-size:20px;margin:0 0 10px">404 · 结果文件不存在</h2>' +
          '<p style="font-size:14px;color:#6b7280;margin:0 0 6px">该岗位的结果页未生成或已被清理。</p>' +
          '<p style="font-size:13px;color:#9ca3af;margin:0">请回到生成面板：对失败文件点「重试」，或修改参数后重新一键生成。</p></body></html>';
        res.writeHead(404, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-cache" });
        res.end(body); return;
      }
      res.writeHead(404, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-cache" });
      res.end(JSON.stringify({ error: "文件不存在：" + filePath }));
      return;
    }
    const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
      ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
      ".md": "text/plain; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml" };
    // Cache-Control: no-cache → 每次重新校验，避免浏览器用缓存旧版 index.html/app.js（此前更新后不生效/按钮失灵）
    res.writeHead(200, { "Content-Type": types[path.extname(filePath).toLowerCase()] || "application/octet-stream",
      "Cache-Control": "no-cache" });
    res.end(data);
  });
}

// ================= 服务入口 =================
http.createServer((req, res) => {
  // 客户端断连等异步错误不崩溃（P0-3）
  res.on("error", () => {});
  const url = new URL(req.url, "http://localhost:" + port);
  let p;
  try { p = decodeURIComponent(url.pathname); } // P0-1：畸形百分号编码返回 400，不崩进程
  catch (e) { res.writeHead(400); res.end("Bad Request"); return; }

  // API
  if (p.startsWith("/api/")) return handleApi(req, res, url);

  // 预览：/preview/<公司>/<文件>
  const previewMatch = /^\/preview\/([^/]+)\/(.+)$/.exec(p);
  if (previewMatch) {
    let comp, file;
    try { comp = decodeURIComponent(previewMatch[1]); file = decodeURIComponent(previewMatch[2]); }
    catch (e) { res.writeHead(400); res.end("Bad Request"); return; }
    // 岗位名校验（P0-2）：与 /api/material 同规则，拒绝 . / .. 逃逸
    if (!/^(?!\.{1,2}$)[^\\\/:*?"<>|\u0000-\u001f]{1,80}$/.test(comp)) {
      res.writeHead(403); res.end("Forbidden"); return;
    }
    // 防路径穿越：只允许访问 30_产出/面试材料/<公司>/ 内文件
    const base = path.resolve(MATERIALS, comp);
    const target = path.resolve(base, file);
    if (!target.startsWith(path.resolve(base) + path.sep) && target !== path.resolve(base)) {
      res.writeHead(403); res.end("Forbidden"); return;
    }
    // 产物重命名容错（R12）：请求的固定文件名不存在时，回退到目录内第一个 .html（用户重命名后的结果页仍可预览）
    if (!fs.existsSync(target)) {
      let fallback = null;
      try {
        fallback = fs.readdirSync(base).filter(f => /\.html$/i.test(f))[0] || null;
      } catch (e) { fallback = null; }
      return serveStatic(res, fallback ? path.join(base, fallback) : target);
    }
    return serveStatic(res, target);
  }

  // 前端面板
  if (p === "/" || p === "/web" || p === "/web/") return serveStatic(res, path.join(TOOLS, "web", "index.html"));

  // 静态：20_执行 下其他文件（如 /index.html 为旧入口 → 面板）
  if (p === "/index.html") return serveStatic(res, path.join(TOOLS, "web", "index.html"));
  if (p.startsWith("/web/")) {
    // 固定根包含检查（P0-2）：拒绝 .. 逃逸出 20_执行 目录
    const f = path.resolve(TOOLS, p.slice(1));
    if (!f.startsWith(TOOLS + path.sep)) { res.writeHead(403); res.end("Forbidden"); return; }
    return serveStatic(res, f);
  }

  const safe = path.resolve(TOOLS, "." + p);
  if (!safe.startsWith(TOOLS + path.sep)) { res.writeHead(403); res.end("Forbidden"); return; }
  // 敏感文件禁止静态读取（P0-4）：config.json（含明文 apiKey）及其备份
  const baseName = path.basename(safe);
  if (/config\.json/i.test(baseName) || /\.bak([-.\d]*)?$/i.test(baseName)) {
    res.writeHead(403); res.end("Forbidden"); return;
  }
  return serveStatic(res, safe);
}).listen(port, "127.0.0.1", () => {
  // D4 修复：启动时恢复历史任务（_task_store.json），重启后 taskId 仍可查询/重试
  loadStore();
  console.log("面试准备助手（纯文本版）服务已启动: http://127.0.0.1:" + port + "（仅本机可访问）");
  console.log("已尝试自动打开浏览器；如未打开，请手动访问 http://127.0.0.1:" + port);
  // E-2：自动打开默认浏览器（仅 Windows，失败不影响使用）
  try {
    require("child_process").spawn("cmd", ["/c", "start", "http://127.0.0.1:" + port], { detached: true, stdio: "ignore" }).unref();
  } catch (e) { /* 忽略 */ }
});
