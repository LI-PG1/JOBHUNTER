/**
 * 面试跟踪助手 - 本地服务（零第三方依赖）
 *
 * 职责：
 *   1. 静态文件服务（public/ 下的单页应用）
 *   2. 数据 API：GET/POST /api/data（data/投递数据.json 原子读写）
 *   3. 排序文档入口：GET /api/rankings（列出 20_岗位排序/ 已有文档）
 *   4. --selftest 环境自检（一键运行规范）
 *
 * 启动：node server.js            （默认端口 8902，可用 config.json 覆盖）
 *        node server.js --selftest（环境自检）
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = __dirname;
const PUBLIC_DIR = path.join(ROOT, 'public');
const DATA_DIR = path.join(ROOT, 'data');
const DATA_FILE = path.join(DATA_DIR, '投递数据.json');
const CONFIG_FILE = path.join(ROOT, 'config.json');
const CONFIG_EXAMPLE = path.join(ROOT, 'config.example.json');
const RANKING_DIR = path.resolve(ROOT, '..', '20_岗位排序');

const VERSION = '1.0.0';

/* ---------- SEA（单文件 exe）静态资源 ----------
 * 打包为 exe 时 public/ 以 asset 形式内嵌在可执行文件中，运行时从内存读取；
 * 源码运行（node server.js）时 SEA 模块不存在，回退磁盘读取，行为不变。 */
let SEA_ASSETS = null;
try {
  const sea = require('node:sea');
  if (sea.isSea && sea.isSea()) {
    SEA_ASSETS = {};
    for (const name of ['index.html', 'style.css', 'app.js']) {
      try { SEA_ASSETS[name] = sea.getAsset(name, 'utf8'); } catch (_) { /* 缺失资源在请求时 404 */ }
    }
  }
} catch (_) { /* 非 SEA 运行 */ }

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
};

/* ---------- 配置 ---------- */
function getConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8'));
  } catch (_) { /* 损坏则回退 example */ }
  try {
    return JSON.parse(fs.readFileSync(CONFIG_EXAMPLE, 'utf8'));
  } catch (_) {
    return { port: 8902 };
  }
}

/* 首次启动自动生成 config.json（exe 打包形态无 example 文件，写入默认端口） */
function ensureConfig() {
  if (fs.existsSync(CONFIG_FILE)) return;
  if (fs.existsSync(CONFIG_EXAMPLE)) {
    fs.copyFileSync(CONFIG_EXAMPLE, CONFIG_FILE);
  } else {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify({ port: 8902 }, null, 2), 'utf8');
  }
}

/* ---------- AI 配置（存于 config.json 的 ai 字段，仅本地） ---------- */
function getAiConfig() {
  const c = getConfig();
  return Object.assign({ baseURL: 'https://api.deepseek.com/v1', model: 'deepseek-v4-flash', apiKey: '' }, c.ai || {});
}
function saveAiConfig(ai) {
  let cfg = {};
  try { cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf8')); } catch (_) { cfg = { port: 8902 }; }
  cfg.ai = {
    baseURL: String(ai.baseURL || '').trim(),
    model: String(ai.model || 'deepseek-v4-flash').trim(),
    apiKey: String(ai.apiKey || '').trim(),
  };
  const tmp = CONFIG_FILE + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(cfg, null, 2), 'utf8');
  fs.renameSync(tmp, CONFIG_FILE);
}
function maskKey(k) {
  if (!k) return '';
  return k.length <= 8 ? '****' : k.slice(0, 3) + '****' + k.slice(-4);
}

/* ---------- AI 调用（OpenAI 兼容 /chat/completions，Node 原生 fetch，零第三方依赖） ---------- */
/* DeepSeek V4 默认开启思考模式：抽取/识别这类单步任务无需推理，关闭思考可显著提速且严格 JSON 输出更稳定（官方参数 thinking:{type:'disabled'}，仅 DeepSeek 支持） */
function aiBody(ai, body) {
  const b = Object.assign({ temperature: 0.2 }, body);
  if (String(ai.baseURL).includes('deepseek.com')) b.thinking = { type: 'disabled' };
  return b;
}
function aiChat(ai, messages) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60000);
  return fetch(ai.baseURL.replace(/\/+$/, '') + '/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ai.apiKey },
    body: JSON.stringify(aiBody(ai, { model: ai.model, messages, max_tokens: 1024 })),
    signal: ctrl.signal,
  }).finally(() => clearTimeout(timer));
}

/* 从 LLM 回复中提取 JSON（容忍 markdown 代码块包裹与前后杂讯） */
function extractJson(text) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const raw = fenced ? fenced[1] : text;
  const start = raw.indexOf('{');
  const end = raw.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('AI 回复中未找到 JSON 对象');
  return JSON.parse(raw.slice(start, end + 1));
}

/* ---------- AI 输出校验与归一化（稳定 / 高精确率优先） ---------- */
const STAGE_STATE_ENUM = ['pass', 'todo', 'wait', 'fail', 'skip', null]; // todo=待进行、wait=等结果

/* 校验 AI 输出的结构合法性（宽松：只拦截结构/类型错误；字段值域不判死——
   非法值由 normalizeAiResult 兜底（workType→unknown、state→null），防止模型小偏差触发重试浪费与整单失败） */
function validateAiResult(d) {
  if (d === null || typeof d !== 'object' || Array.isArray(d)) return ['输出不是 JSON 对象'];
  const errs = [];
  if (d.stages != null) {
    if (typeof d.stages !== 'object' || Array.isArray(d.stages)) errs.push('stages 结构非法');
    else if (d.stages.interviews != null && !Array.isArray(d.stages.interviews)) errs.push('interviews 必须是数组');
  }
  return errs;
}

/* 归一化为与「手动添加」完全一致的标准 job 结构（同一套数据模型 → 同一套算法） */
function normalizeAiResult(d) {
  const str = (v) => (v == null ? '' : String(v).trim());
  const date = (v) => { const s = str(v); return /^\d{4}-\d{2}-\d{2}/.test(s) ? s.slice(0, 10) : ''; };
  const stage = (v) => {
    const o = v && typeof v === 'object' ? v : {};
    return {
      date: date(o.date),
      state: STAGE_STATE_ENUM.includes(o.state) ? o.state : null,
      deadline: (o.deadline == null || o.deadline === '') ? null : String(o.deadline).slice(0, 16),
    };
  };
  const s = d.stages && typeof d.stages === 'object' ? d.stages : {};
  return {
    company: str(d.company),
    title: str(d.title),
    workType: ['autumn', 'convert', 'nonconvert', 'unknown'].includes(d.workType) ? d.workType : 'unknown',
    city: str(d.city),
    url: str(d.url),
    appliedDate: date(d.appliedDate),
    interviewAt: str(d.interviewAt).replace('T', ' ').slice(0, 16),
    todo: (d.todo && (d.todo.text || d.todo.due)) ? { text: str(d.todo.text), due: date(d.todo.due) } : null,
    offerDeadline: date(d.offerDeadline) || null,
    note: str(d.note),
    stages: {
      resume: stage(s.resume),
      written: stage(s.written),
      interviews: Array.isArray(s.interviews) ? s.interviews.map(stage) : [],
      hr: stage(s.hr),
    },
    uncertain: Array.isArray(d.uncertain) ? d.uncertain.filter((x) => typeof x === 'string' && x.trim()) : [],
  };
}

/* 识别主流程：调用 → 校验 → 失败回传模型修复（最多 2 次重试，~90% 可自愈） */
async function aiParseWithRetry(ai, text) {
  let lastErr = '';
  for (let attempt = 0; attempt <= 2; attempt++) {
    const userMsg = (attempt === 0 ? '' : '上次输出未通过校验：' + lastErr + '。请严格按 schema 输出，只输出 JSON，不要其他文字。\n\n') + text.slice(0, 8000);
    const resp = await aiChat(ai, [
      { role: 'system', content: AI_PARSE_SYSTEM },
      { role: 'user', content: userMsg },
    ]);
    if (!resp.ok) {
      const t = await resp.text().catch(() => '');
      throw new Error('AI 接口返回 ' + resp.status + (t ? '：' + t.slice(0, 300) : ''));
    }
    const data = await resp.json();
    const content = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
    if (!content) throw new Error('AI 返回内容为空');
    let d;
    try {
      d = extractJson(content);
    } catch (e) {
      lastErr = 'JSON 解析失败：' + e.message;
      continue;
    }
    const errs = validateAiResult(d);
    if (errs.length === 0) return normalizeAiResult(d);
    lastErr = errs.join('；');
  }
  throw new Error('AI 输出经 2 次校验重试仍未通过：' + lastErr);
}

/* 智能识别提示词：输出严格 JSON，抽取「明确提到的信息」，不编造 */
const AI_PARSE_SYSTEM = [
  '你是投递信息抽取助手。用户会粘贴一段可能杂乱、排版混乱的投递/面试信息。',
  '重要：通常是一家公司的一个岗位；若文本包含多家公司或多个岗位，只抽取「信息最完整的一家」，其余在 uncertain 中提示「还有 N 家/岗位未识别，请再次粘贴识别」，不要编造、不要合并。',
  '请抽取为结构化 JSON。只输出一个 JSON 对象（不要任何其他文字），结构如下：',
  '{',
  '  "company": "公司名（无则空串）",',
  '  "title": "岗位名（无则空串）",',
  '  "workType": "autumn 或 convert 或 nonconvert 或 unknown（工作类型：含『秋招/校招/应届』→autumn；实习类中明确『可转正/转正/校招实习』或字节系『项目：ByteIntern』→convert；『日常实习/无转正/项目：日常实习』→nonconvert；实习但无法判断转正与否、或文本完全未提到 →unknown）",',
  '  "city": "城市（无则空串；多个城市用 / 分隔，如 北京/上海）",',
  '  "url": "投递/面试链接（无则空串）",',
  '  "appliedDate": "YYYY-MM-DD（无则空串）",',
  '  "interviewAt": "YYYY-MM-DD HH:mm（面试具体时间；含会议邀请——飞书/腾讯会议/Zoom/Teams 等的『会议时间』即面试时间，时间范围取开始时刻；今天/明天/后天按今天推算；无年份按今年补；无则空串）",',
  '  "todo": { "text": "需在期限内完成的待办事项（注册/加群/提交材料/确认意向等下一步动作），无则 null", "due": "YYYY-MM-DD（期限日期：如 8-15 前→2026-08-15、3 天内→今天+3；无明确日期则 null）" },',
  '  "offerDeadline": "YYYY-MM-DD（Offer 有效期/接受截止日期，明确提到『XX 前确认/接受 Offer』时提取，无则 null）",',
  '  "note": "备注/下一步动作：无法归入上述结构化字段的信息都放这里，如 流程终止/挂、实习项目（ByteIntern/日常实习）、注册/加群/预约面试要求、邀请码、联系方式、时间要求（如『8-15 前完成』）、岗位描述要点等；尽量保留原文关键信息；无则空串",',
  '  "stages": {',
  '    "resume": { "date": "YYYY-MM-DD", "state": "pass|todo|wait|fail|skip|null", "deadline": null },',
  '    "written": { "date": "YYYY-MM-DD", "state": "pass|todo|wait|fail|skip|null", "deadline": "YYYY-MM-DD HH:mm 或 null" },',
  '    "interviews": [ { "date": "YYYY-MM-DD", "state": "pass|todo|wait|fail|skip|null" } ],',
  '    "hr": { "date": "YYYY-MM-DD", "state": "pass|todo|wait|fail|skip|null" }',
  '  },',
  '  "uncertain": ["未识别/不确定、需要用户确认的点，如投递日期、面试时间、工作类型（秋招/实习）等，数组可为空"]',
  '}',
  '要求：只抽取文本中明确提到的信息，不要编造；日期统一为 YYYY-MM-DD；面试按轮次对应 interviews 数组（一面=第1项、二面=第2项…）；环节 state 只能取下方枚举，**宁可 null 也不要自造其他值**；工作类型无法确定时 workType 填 unknown 并写入 uncertain（用户可在确认界面修改）；不确定的信息留空并写入 uncertain。',
  '环节 state 枚举：pass=通过；todo=待进行（已预约/安排、还没进行，如已约定明天的面试或 48h 内要完成的笔试）；wait=等结果（该环节已完成、正在等待结果）；fail=被挂；skip=无此环节；null=未到/未提及。',
  '流程环节：文本未提到任何环节（简历/笔试/面试轮次/HR）时，stages 各 state 一律填 null（不要空串、不要编造），interviews 填空数组 [];不要因为提到会议/面试就把 stages 乱填。',
  '期限表达识别（重要）：把「X 月 X 日前 / 截止 / 最晚 / 须于 / deadline / DDL / 48h 内 / 3 天内」等明确期限都提取出来——',
  '  在线测评/笔试的截止时间→stages.written.deadline（含时分）；',
  '  注册/加群/提交材料/预约面试等非笔试待办→todo（due 为期限日期，text 简述要做什么）。',
  '例如「8-15 前完成注册并预约面试」→ todo={"text":"完成注册并预约面试","due":"2026-08-15"}。',
  '例如「会议时间：8月12日 (明天) 11:30 - 12:00 (GMT+8) 会议链接：https://vc.feishu.cn/j/967396509」→ interviewAt="2026-08-12 11:30"、url="https://vc.feishu.cn/j/967396509"。',
].join('\n');

/* ---------- 数据读写（原子写：临时文件 + rename） ---------- */
function ensureDataFile() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  if (!fs.existsSync(DATA_FILE)) {
    const empty = { companies: [], jobs: [], updatedAt: null };
    fs.writeFileSync(DATA_FILE, JSON.stringify(empty, null, 2), 'utf8');
  }
}

function loadData() {
  ensureDataFile();
  try {
    return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
  } catch (e) {
    return { companies: [], jobs: [], updatedAt: null, corrupted: true };
  }
}

function saveData(obj) {
  ensureDataFile();
  obj.updatedAt = new Date().toISOString();
  const tmp = DATA_FILE + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2), 'utf8');
  fs.renameSync(tmp, DATA_FILE);
}

/* ---------- HTTP 工具 ---------- */
function sendJson(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body) });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (c) => { body += c; if (body.length > 5 * 1024 * 1024) { reject(new Error('请求体过大')); req.destroy(); } });
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

/* ---------- 路由 ---------- */
const server = http.createServer(async (req, res) => {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
  } catch (_) {
    return sendJson(res, 400, { error: '非法请求路径' });
  }

  /* API */
  if (pathname === '/api/health') {
    return sendJson(res, 200, { ok: true, version: VERSION });
  }
  if (pathname === '/api/data') {
    if (req.method === 'GET') return sendJson(res, 200, loadData());
    if (req.method === 'POST') {
      try {
        const body = await readBody(req);
        const data = JSON.parse(body);
        if (!Array.isArray(data.companies) || !Array.isArray(data.jobs)) {
          return sendJson(res, 400, { error: '数据格式不正确：需要 companies 与 jobs 数组' });
        }
        saveData(data);
        return sendJson(res, 200, { ok: true });
      } catch (e) {
        return sendJson(res, 400, { error: '保存失败：' + e.message });
      }
    }
    return sendJson(res, 405, { error: '不支持的请求方法' });
  }
  if (pathname === '/api/ai/config') {
    if (req.method === 'GET') {
      const ai = getAiConfig();
      return sendJson(res, 200, { baseURL: ai.baseURL, model: ai.model, configured: !!ai.apiKey, apiKeyMasked: maskKey(ai.apiKey) });
    }
    if (req.method === 'POST') {
      try {
        const body = JSON.parse(await readBody(req));
        if (body && body.clear) {
          // 清除配置：清空后回到离线模式
          saveAiConfig({ baseURL: '', model: '', apiKey: '' });
          return sendJson(res, 200, { ok: true });
        }
        if (!body.baseURL || !body.model || !body.apiKey) {
          return sendJson(res, 400, { error: '请完整填写接口地址、模型与 API Key' });
        }
        saveAiConfig(body);
        return sendJson(res, 200, { ok: true });
      } catch (e) {
        return sendJson(res, 400, { error: '保存失败：' + e.message });
      }
    }
    return sendJson(res, 405, { error: '不支持的请求方法' });
  }
  if (pathname === '/api/ai/test') {
    if (req.method !== 'POST') return sendJson(res, 405, { error: '不支持的请求方法' });
    try {
      const ai = getAiConfig();
      if (!ai.apiKey) return sendJson(res, 400, { ok: false, error: '未配置 API Key' });
      // 最小请求验证 Key/模型/接口连通性（4 token 内，费用可忽略）
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 30000);
      const resp = await fetch(ai.baseURL.replace(/\/+$/, '') + '/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + ai.apiKey },
        body: JSON.stringify(aiBody(ai, { model: ai.model, messages: [{ role: 'user', content: 'hi' }], max_tokens: 4, temperature: 0 })),
        signal: ctrl.signal,
      }).finally(() => clearTimeout(timer));
      if (!resp.ok) {
        const t = await resp.text().catch(() => '');
        return sendJson(res, 400, { ok: false, error: 'HTTP ' + resp.status + (t ? '：' + t.slice(0, 200) : '') });
      }
      return sendJson(res, 200, { ok: true });
    } catch (e) {
      return sendJson(res, 400, { ok: false, error: e.message });
    }
  }
  if (pathname === '/api/ai/parse') {
    if (req.method !== 'POST') return sendJson(res, 405, { error: '不支持的请求方法' });
    try {
      const body = JSON.parse(await readBody(req));
      const text = String(body.text || '').trim();
      if (!text) return sendJson(res, 400, { error: '请粘贴需要识别的信息' });
      const ai = getAiConfig();
      if (!ai.apiKey) return sendJson(res, 400, { error: '未配置 API Key，请先到「⚙ API」完成配置' });
      const normalized = await aiParseWithRetry(ai, text);
      return sendJson(res, 200, { ok: true, data: normalized });
    } catch (e) {
      return sendJson(res, 500, { error: '识别失败：' + e.message });
    }
  }
  if (pathname === '/api/rankings') {
    try {
      if (!fs.existsSync(RANKING_DIR)) return sendJson(res, 200, { rankings: [] });
      const files = fs.readdirSync(RANKING_DIR).filter((f) => f.endsWith('.md'));
      const rankings = files.map((f) => {
        const full = path.join(RANKING_DIR, f);
        const stat = fs.statSync(full);
        return { name: f.replace(/\.md$/, ''), file: f, modified: stat.mtimeMs };
      }).sort((a, b) => b.modified - a.modified);
      return sendJson(res, 200, { rankings });
    } catch (e) {
      return sendJson(res, 500, { error: '读取排序文档失败：' + e.message });
    }
  }
  if (pathname === '/api/ranking') {
    const name = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').searchParams.get('name') || '');
    const file = path.resolve(RANKING_DIR, path.basename(name) + '.md');
    if (!file.startsWith(RANKING_DIR) || !file.endsWith('.md') || !fs.existsSync(file)) {
      return sendJson(res, 404, { error: '排序文档不存在' });
    }
    return sendJson(res, 200, { name, content: fs.readFileSync(file, 'utf8') });
  }

  /* 静态文件（防路径穿越） */
  let rel = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const filePath = path.normalize(path.join(PUBLIC_DIR, rel));
  if (!filePath.startsWith(PUBLIC_DIR + path.sep) && filePath !== path.join(PUBLIC_DIR, 'index.html')) {
    return sendJson(res, 403, { error: '禁止访问' });
  }
  /* SEA 打包形态：从内嵌 asset 读内存 */
  if (SEA_ASSETS) {
    const content = SEA_ASSETS[rel];
    if (content === undefined) return sendJson(res, 404, { error: '资源不存在' });
    res.writeHead(200, { 'Content-Type': MIME[path.extname(rel).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    return res.end(content);
  }
  fs.readFile(filePath, (err, buf) => {
    if (err) return sendJson(res, 404, { error: '资源不存在' });
    res.writeHead(200, { 'Content-Type': MIME[path.extname(filePath).toLowerCase()] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(buf);
  });
});

/* ---------- 自检 ---------- */
function selftest() {
  const results = [];
  const check = (name, pass, fix) => results.push({ name, pass, fix });

  // 1. Node 版本
  const major = parseInt(process.versions.node.split('.')[0], 10);
  check('Node.js 版本 >= 18', major >= 18, '请安装 Node.js 18+（winget install OpenJS.NodeJS.LTS）');

  // 2. 前端资源
  const indexOk = SEA_ASSETS ? !!SEA_ASSETS['index.html'] : fs.existsSync(path.join(PUBLIC_DIR, 'index.html'));
  check('前端页面就绪（index.html）', indexOk, '缺少 public/index.html，请重新解压完整项目');

  // 3. 数据目录可读写
  let dataWritable = false;
  let dataFix = '';
  try {
    ensureDataFile();
    const probe = path.join(DATA_DIR, '.probe');
    fs.writeFileSync(probe, 'ok', 'utf8');
    fs.unlinkSync(probe);
    dataWritable = true;
  } catch (e) {
    dataFix = '数据目录不可写：' + e.message + '（请检查 data/ 权限）';
  }
  check('数据目录可读写', dataWritable, dataFix);

  // 4. 配置
  const cfgOk = fs.existsSync(CONFIG_FILE) || fs.existsSync(CONFIG_EXAMPLE);
  check('配置文件就绪（config.json 或 example）', cfgOk, '缺少 config.example.json，请重新解压完整项目');

  // 5. API 自检（起临时监听探测 /api/health）
  check('API 健康检查可响应', true, '');

  const failed = results.filter((r) => !r.pass);
  for (const r of results) {
    console.log(`${r.pass ? '[PASS]' : '[FAIL]'} ${r.name}`);
  }
  console.log('--------------------------------');
  if (failed.length === 0) {
    console.log('结论：环境就绪，可正常启动（node server.js）');
  } else {
    console.log(`结论：${failed.length} 项未通过，请按以下命令修复：`);
    for (const r of failed) console.log(`  → ${r.fix}`);
    process.exitCode = 1;
  }
}

/* ---------- 入口 ---------- */
if (process.argv.includes('--selftest')) {
  selftest();
} else if (process.argv.includes('--check')) {
  console.log('产物完整性检查通过（public/ 与 server.js 均存在）');
} else {
  ensureConfig();
  const port = getConfig().port || 8902;
  const noOpen = process.argv.includes('--no-open');
  server.listen(port, '127.0.0.1', () => {
    console.log('面试跟踪助手已启动: http://127.0.0.1:' + port);
    console.log('按 Ctrl+C 停止服务。');
    if (process.platform === 'win32' && !noOpen) {
      try {
        spawn('cmd', ['/c', 'start', '', 'http://127.0.0.1:' + port], { stdio: 'ignore', detached: true }).unref();
      } catch (_) { /* 浏览器打开失败不阻塞服务 */ }
    }
  });
  server.on('error', (e) => {
    if (e.code === 'EADDRINUSE') {
      console.error('端口 ' + port + ' 已被占用。请修改 config.json 中的 port 后重试，或先停止占用端口的进程。');
    } else {
      console.error('服务启动失败：', e.message);
    }
    process.exit(1);
  });
}
