/* JobHunter 求职助手 v0.2 —— 四大板块 + 左栏流程引导 + 控制台
 * 对齐子板块（JS-Agent/JL-Agent）前端模式；工程字段全部折叠或翻译 */
"use strict";

const $ = (id) => document.getElementById(id);
const SAVED_KEY = "jobhunter_saved_jobs";
const TRACK_KEY = "jobhunter_tracks";

/* ================= 板块定义（顶部常驻导航 + 左栏流程） ================= */
const BOARDS = {
  resume: {
    label: "简历生成",
    note: "把经历写详细，简历与匹配才会准。",
    steps: [
      { n: 1, t: "填写画像", d: "教育 / 项目 / 实习工作 / 技能" },
      { n: 2, t: "生成并预览", d: "一键生成完整简历" },
      { n: 3, t: "版本与导出", d: "上传 / 粘贴简历，导出 PDF" },
    ],
  },
  match: {
    label: "岗位匹配",
    note: "基于你的画像搜索岗位并给出匹配度。",
    steps: [
      { n: 1, t: "匹配画像", d: "自动带出简历画像" },
      { n: 2, t: "岗位清单", d: "匹配度与详情" },
      { n: 3, t: "收藏与投递", d: "投递清单雏形" },
    ],
  },
  interview: {
    label: "面试准备",
    note: "面试材料与复盘，来自大脑面试环节。",
    steps: [
      { n: 1, t: "面试材料", d: "生成并查看材料" },
      { n: 2, t: "面试复盘", d: "复盘报告" },
    ],
  },
  tracker: {
    label: "面试跟踪",
    note: "投递进度、面试节点与提醒，保存在本机浏览器。",
    steps: [
      { n: 1, t: "今日要点", d: "置顶与未来 7 天提醒" },
      { n: 2, t: "新增与筛选", d: "智能识别 / 手动新增 / 分类筛选" },
      { n: 3, t: "投递列表", d: "分组与紧迫性排序" },
    ],
  },
};

let curBoard = "resume";

function renderRail() {
  const b = BOARDS[curBoard];
  const steps = b.steps.map((s) => `
    <li class="pstep" data-b="${curBoard}" data-step="${s.n}">
      <span class="p-no">${s.n}</span>
      <div class="p-txt"><b>${s.t}</b><em>${s.d}</em></div>
    </li>`).join("");
  $("railSteps").innerHTML = steps;
  $("railNote").textContent = b.note;
  document.querySelectorAll("#railSteps .pstep").forEach((el) => {
    el.addEventListener("click", () => {
      document.querySelectorAll(`#board-${curBoard} .card`).forEach((c) => c.classList.remove("active"));
      const target = document.querySelector(`#board-${curBoard} .card[data-step="${el.dataset.step}"]`);
      if (target) target.classList.add("active");
    });
  });
  // 左栏步骤高亮 = 主内容当前激活卡片
  document.querySelectorAll("#railSteps .pstep").forEach((el) => {
    const card = document.querySelector(`#board-${curBoard} .card[data-step="${el.dataset.step}"]`);
    el.classList.toggle("active", card && card.classList.contains("active"));
  });
  renderResumeManage();
}

function switchBoard(name) {
  curBoard = name;
  document.querySelectorAll(".bnav").forEach((b) => b.classList.toggle("active", b.dataset.board === name));
  document.querySelectorAll(".board").forEach((p) => { p.hidden = p.id !== "board-" + name; });
  // 激活该板块第 1 个步骤卡片
  const first = document.querySelector(`#board-${name} .card`);
  document.querySelectorAll(`#board-${name} .card`).forEach((c) => c.classList.remove("active"));
  if (first) first.classList.add("active");
  renderRail();
  if (name === "resume") renderResumeVers();
  if (name === "match") { renderVersionOptions($("inpResumeVer")); autoFillProfileText(); renderSaved(); }
  if (name === "tracker") trkInitRender();
  if (name === "interview") { renderVersionOptions($("inpIntVer")); renderInterviewCached(); }
}
document.querySelectorAll(".bnav").forEach((b) => b.addEventListener("click", () => {
  switchBoard(b.dataset.board);
  // 顶栏切板块视同进入该板块：收起着陆页（品牌点击可随时返回）
  $("landing").classList.add("hidden");
}));

/* ================= 着陆页：选择进入哪个板块 ================= */
const BOARD_ICON = { resume: "📄", match: "🎯", interview: "🎤", tracker: "📋" };
function enterBoard(name) {
  switchBoard(name);
  $("landing").classList.add("hidden");
}
function renderLanding() {
  const grid = $("landingGrid");
  grid.innerHTML = Object.entries(BOARDS).map(([k, b]) => `
    <button class="landing-card" data-board="${k}">
      <div class="lc-icon">${BOARD_ICON[k] || "📦"}</div>
      <b>${esc(b.label)}</b>
      <p>${esc(b.note)}</p>
    </button>`).join("");
  grid.querySelectorAll(".landing-card").forEach((c) => c.addEventListener("click", () => enterBoard(c.dataset.board)));
  $("brandHome").addEventListener("click", () => $("landing").classList.remove("hidden"));
  $("btnLandingConsole").addEventListener("click", () => { $("consoleMask").classList.remove("hidden"); loadConsole(); });
}

/* ================= 简历管理（左栏常驻：手动增删，增删均需确认） ================= */
function renderResumeManage() {
  const box = $("railResume");
  if (!box) return;
  const list = resumeVersions();
  const activeId = localStorage.getItem(ACTIVE_RESUME_KEY);
  box.innerHTML = `
    <div class="rm-head">
      <span>📄 简历管理</span>
      <button class="btn btn-sm btn-ghost" id="rmToggleAdd" type="button">＋ 新增</button>
    </div>
    <div class="rm-add hidden" id="rmAdd">
      <input type="file" id="rmFile" accept=".pdf,.txt,.md,.text" class="hidden">
      <button class="btn btn-ghost btn-sm" id="rmPickFile" type="button">📄 上传 txt / md / PDF</button>
      <textarea id="rmPaste" class="input" rows="3" placeholder="或直接粘贴简历文本…"></textarea>
      <button class="btn btn-primary btn-sm" id="rmSavePaste" type="button">＋ 保存为版本</button>
    </div>
    <div class="rm-list">${list.map((v) => `
      <div class="ver-item ${v.id === activeId ? "active" : ""}">
        <span class="ver-letter">${v.letter}</span>
        <div class="ver-info"><b>${esc(v.name)}</b>
          <em>${v.source === "upload" ? "上传 / 粘贴" : "表单生成"} · ${(v.text || "").length} 字</em>
        </div>
        <button class="btn-link rm-pick" data-pick="${v.id}">${v.id === activeId ? "✓ 使用中" : "选用"}</button>
        <button class="btn-link btn-del-row rm-del" data-del="${v.id}">删除</button>
      </div>`).join("") || '<div class="empty-hint">暂无简历版本</div>'}</div>`;
  $("rmToggleAdd").addEventListener("click", () => $("rmAdd").classList.toggle("hidden"));
  $("rmPickFile").addEventListener("click", () => $("rmFile").click());
  $("rmFile").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    if (!confirm(`确认将「${f.name}」保存为简历版本？`)) { e.target.value = ""; return; }
    if (/\.pdf$/i.test(f.name)) {
      const fd = new FormData();
      fd.append("file", f);
      $("rmPickFile").textContent = "⏳ 解析 PDF…";
      try {
        const r = await fetch("/api/resume/parse_pdf", { method: "POST", body: fd });
        const d = await r.json();
        if (!r.ok) { trkToast(d.detail || "PDF 解析失败", true); return; }
        addResumeVersion(f.name.replace(/\.pdf$/i, "") + " PDF版", d.text, "upload");
        trkToast(`PDF 解析成功：${d.chars} 字 → 已保存为版本`);
      } catch (err) { trkToast("PDF 解析失败：" + err.message, true); }
      finally { $("rmPickFile").textContent = "📄 上传 txt / md / PDF"; }
      $("rmAdd").classList.add("hidden");
      return;
    }
    const rd = new FileReader();
    rd.onload = () => {
      if (String(rd.result || "").trim()) addResumeVersion(f.name, String(rd.result), "upload");
      $("rmAdd").classList.add("hidden");
    };
    rd.readAsText(f, "utf-8");
  });
  $("rmSavePaste").addEventListener("click", () => {
    const t = $("rmPaste").value.trim();
    if (!t) return;
    if (!confirm("确认将粘贴内容保存为简历版本？")) return;
    addResumeVersion("粘贴简历 " + new Date().toLocaleDateString(), t, "upload");
    $("rmPaste").value = "";
    $("rmAdd").classList.add("hidden");
  });
  box.querySelectorAll(".rm-pick").forEach((b) => b.addEventListener("click", () => setActiveResume(b.dataset.pick)));
  box.querySelectorAll(".rm-del").forEach((b) => b.addEventListener("click", () => {
    const v = resumeVersions().find((x) => x.id === b.dataset.del);
    if (!v) return;
    if (confirm(`确认删除简历「${v.letter} · ${v.name}」？`)) delResumeVersion(v.id);
  }));
}

/* ================= 控制台 modal ================= */
$("btnConsole").addEventListener("click", () => { $("consoleMask").classList.remove("hidden"); loadConsole(); });
$("btnCloseConsole").addEventListener("click", () => $("consoleMask").classList.add("hidden"));
$("consoleMask").addEventListener("click", (e) => { if (e.target === $("consoleMask")) $("consoleMask").classList.add("hidden"); });

/* 厂商 → 可选模型（模型只许从下拉选择，不手输） */
const PROVIDER_MODELS = {
  openai:   { label: "OpenAI",         models: [["gpt-4o-mini", "GPT-4o mini"], ["gpt-4o", "GPT-4o"], ["gpt-5-mini", "GPT-5 mini"], ["gpt-5", "GPT-5"]] },
  deepseek: { label: "DeepSeek",       models: [["deepseek-v4-flash", "DeepSeek-V4-Flash"], ["deepseek-v4-pro", "DeepSeek-V4-Pro"]] },
  qwen:     { label: "通义千问",        models: [["qwen-turbo", "Qwen-Turbo"], ["qwen-plus", "Qwen-Plus"], ["qwen-max", "Qwen-Max"]] },
  zhipu:    { label: "智谱 GLM",       models: [["glm-4-flash", "GLM-4-Flash"], ["glm-4-plus", "GLM-4-Plus"], ["glm-4.5", "GLM-4.5"]] },
  kimi:     { label: "Kimi",           models: [["moonshot-v1-8k", "Moonshot-v1-8k"], ["moonshot-v1-32k", "Moonshot-v1-32k"], ["kimi-k2", "Kimi-K2"]] },
  claude:   { label: "Anthropic",      models: [["claude-sonnet-4-5", "Claude Sonnet 4.5"], ["claude-opus-4-1", "Claude Opus 4.1"], ["claude-haiku-4-5", "Claude Haiku 4.5"]] },
  ollama:   { label: "Ollama 本地",  models: [["llama3.1:8b", "Llama 3.1 8B"], ["qwen2.5:7b", "Qwen2.5 7B"], ["deepseek-r1:7b", "DeepSeek-R1 7B"], ["gemma2:9b", "Gemma2 9B"]] },
};
function renderModels(provider) {
  const sel = $("modelSelect");
  if (!sel) return;
  const cfg = PROVIDER_MODELS[provider];
  sel.innerHTML = cfg ? cfg.models.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join("")
    : `<option value="">该厂商暂无模型</option>`;
}
function providerOfModel(model) {
  for (const [p, cfg] of Object.entries(PROVIDER_MODELS)) {
    if (model && cfg.models.some(([v]) => v === model)) return p;
  }
  return "";
}
$("providerSelect").addEventListener("change", () => renderModels($("providerSelect").value));

async function loadConsole() {
  try {
    const d = await (await fetch("/api/console")).json();
    renderKeyList(d.keys || []);
    $("keyMsg").textContent = d.key_configured ? `当前启用：${d.llm_model || "模型未填"}` : "未启用任何 Key";
    $("keyMsg").className = d.key_configured ? "hint-ok" : "hint-warn";
    // 新增表单默认选中当前启用的厂商与模型（便于快速追加同厂商 Key）
    const savedModel = d.llm_model || "";
    const provider = PROVIDER_MODELS[d.llm_provider] ? d.llm_provider : (providerOfModel(savedModel) || "deepseek");
    $("providerSelect").value = provider;
    renderModels(provider);
    const sel = $("modelSelect");
    if (savedModel && ![...sel.options].some((o) => o.value === savedModel)) sel.add(new Option(savedModel, savedModel));
    if (savedModel) sel.value = savedModel;
    _tools = d.tools || [];
    renderTools();
    renderArtifacts();
  } catch (e) { $("keyMsg").textContent = "控制台加载失败：" + e.message; $("keyMsg").className = "hint-err"; }
}

/* ================= API Key 管理（多 Key，启用互斥） ================= */
function renderKeyList(keys) {
  const box = $("keyList");
  if (!box) return;
  if (!keys.length) {
    box.innerHTML = '<div class="key-empty">暂无 API Key，请在下方新增。</div>';
    return;
  }
  box.innerHTML = keys.map((k) => `
    <div class="key-item ${k.enabled ? "active" : ""}" data-id="${esc(k.id)}">
      <div class="key-main">
        <span class="chip">${esc(k.provider)}</span>
        <div class="key-info"><b>${esc(k.model)}</b><em>${esc(k.api_key)}</em></div>
        ${k.enabled ? '<span class="badge-on">使用中</span>' : ""}
      </div>
      <div class="key-ops">
        <label class="switch" title="${k.enabled ? "停用" : "启用（自动停用其他 Key）"}">
          <input type="checkbox" data-id="${esc(k.id)}" ${k.enabled ? "checked" : ""}>
          <span class="slider"></span>
        </label>
        <button class="btn-link" data-act="test">测试</button>
        <button class="btn-link danger" data-act="del">删除</button>
      </div>
    </div>`).join("");
  box.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.addEventListener("change", () => setKeyEnabled(cb.dataset.id, cb.checked, cb));
  });
  box.querySelectorAll("button[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.closest(".key-item").dataset.id;
      if (btn.dataset.act === "test") testKey(id, btn);
      else if (btn.dataset.act === "del") deleteKey(id);
    });
  });
}

async function setKeyEnabled(id, enabled, cb) {
  try {
    const r = await fetch(`/api/console/key/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
    renderKeyList(d.keys || []);
    $("keyMsg").textContent = enabled ? "已启用，其余 Key 已自动停用" : "已停用";
    $("keyMsg").className = "hint-ok";
  } catch (e) {
    if (cb) cb.checked = !cb.checked;
    $("keyMsg").textContent = "操作失败：" + e.message;
    $("keyMsg").className = "hint-err";
  }
}

async function testKey(id, btn) {
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "测试中…";
  $("keyMsg").textContent = "";
  try {
    const r = await fetch("/api/console/test", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key_id: id }),
    });
    const d = await r.json();
    if (d.ok) {
      $("keyMsg").textContent = `✓ 连通正常 ${d.latency_ms}ms · ${d.base_url}`;
      $("keyMsg").className = "hint-ok";
    } else {
      $("keyMsg").textContent = `✗ ${d.error || "连接失败"}${d.detail ? " · " + d.detail.slice(0, 120) : ""}`;
      $("keyMsg").className = "hint-err";
    }
  } catch (e) {
    $("keyMsg").textContent = "测试失败：" + e.message;
    $("keyMsg").className = "hint-err";
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

async function deleteKey(id) {
  const el = document.querySelector(`#keyList .key-item[data-id="${id}"]`);
  const model = el ? el.querySelector(".key-info b").textContent : "";
  if (!confirm(`确认删除该 API Key（${model}）？`)) return;
  try {
    const r = await fetch(`/api/console/key/${id}`, { method: "DELETE" });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
    renderKeyList(d.keys || []);
    $("keyMsg").textContent = "已删除";
    $("keyMsg").className = "hint-ok";
  } catch (e) {
    $("keyMsg").textContent = "删除失败：" + e.message;
    $("keyMsg").className = "hint-err";
  }
}

/* 新增 Key：首个自动启用，其余默认停用待手动启用 */
$("btnSaveKey").addEventListener("click", async () => {
  try {
    const r = await fetch("/api/console/key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: $("apiKeyInput").value, model: $("modelSelect").value, provider: $("providerSelect").value }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
    $("apiKeyInput").value = "";
    renderKeyList(d.keys || []);
    $("keyMsg").textContent = d.key.enabled ? "已新增并启用" : "已新增，点击开关启用";
    $("keyMsg").className = "hint-ok";
  } catch (e) { $("keyMsg").textContent = "保存失败：" + e.message; $("keyMsg").className = "hint-err"; }
});

/* ================= 生成文件版本管理（控制台集中管理各板块产物） ================= */
const ART_KEY = "jobhunter_artifacts";
function getArtifacts() { try { return JSON.parse(localStorage.getItem(ART_KEY) || "{}"); } catch { return {}; } }
function saveArtifacts(a) { localStorage.setItem(ART_KEY, JSON.stringify(a)); }
function saveArtifact(kind, name, data) {
  const a = getArtifacts();
  a[kind] = a[kind] || [];
  a[kind].push({ id: Date.now().toString(36), name, time: new Date().toISOString(), data });
  if (a[kind].length > 12) a[kind].shift();
  saveArtifacts(a);
}
function delArtifact(kind, id) {
  const a = getArtifacts();
  a[kind] = (a[kind] || []).filter((x) => x.id !== id);
  saveArtifacts(a);
  renderArtifacts();
}
/* 选用：把历史版本恢复到对应板块的内存缓存 */
function pickMaterial(id) {
  const x = (getArtifacts().materials || []).find((m) => m.id === id);
  if (!x) return;
  window._runData = Object.assign({}, window._runData, { interview_materials: x.data });
  renderInterviewCached();
  trkToast("已选用面试材料：" + x.name);
}
function pickMsr(id) {
  const x = (getArtifacts().msrs || []).find((m) => m.id === id);
  if (!x) return;
  window._runData = Object.assign({}, window._runData, { msr_report: x.data });
  renderInterviewCached();
  trkToast("已选用复盘报告：" + x.name);
}
function pickJobs(id) {
  const x = (getArtifacts().jobs || []).find((m) => m.id === id);
  if (!x) return;
  window._lastJobs = x.data || [];
  $("btnExportCsv").classList.remove("hidden");
  renderJobs(window._lastJobs);
  trkToast("已选用岗位清单：" + x.name);
}
/* renderArtifacts 重构：带类别 data-kind / data-id */
function renderArtifacts2() {
  const box = $("artifactList");
  if (!box) return;
  const a = getArtifacts();
  const activeId = localStorage.getItem(ACTIVE_RESUME_KEY);
  const item = (id, name, meta, picked, acts) => `
    <div class="art-item ${picked ? "active" : ""}" data-id="${id}">
      <div class="art-info"><b>${esc(name)}</b><em>${esc(meta)}</em></div>
      <div class="art-ops">${acts.map(([act, label, cls]) =>
        `<button class="btn-link ${cls || ""}" data-act="${act}">${label}</button>`).join("")}</div>
    </div>`;
  const sec = (kind, icon, title, items) => items.length
    ? `<div class="art-sec" data-kind="${kind}">${icon ? `<div class="art-sec-title">${icon} ${title}</div>` : ""}${items.join("")}</div>`
    : "";
  let html = "";
  html += sec("resume", "📄", "简历", resumeVersions().map((v) => item(v.id, `${v.letter} · ${v.name}`,
    `${(v.text || "").length} 字 · ${(v.updatedAt || "").slice(0, 10)}`, v.id === activeId,
    [["pick", v.id === activeId ? "使用中" : "选用", v.id === activeId ? "dim" : ""], ["del", "删除"]])));
  html += sec("materials", "🎤", "面试材料", (a.materials || []).map((x) => item(x.id, x.name,
    `${(x.time || "").slice(0, 16).replace("T", " ")} · ${x.data && x.data.html ? "1 份 HTML" : "未生成"}`, false,
    [["pick", "选用"], ["del", "删除"]])));
  html += sec("msrs", "📝", "复盘报告", (a.msrs || []).map((x) => item(x.id, x.name,
    `${(x.time || "").slice(0, 16).replace("T", " ")} · ${(x.data && x.data.source) || "未知来源"}`, false,
    [["pick", "选用"], ["del", "删除"]])));
  html += sec("jobs", "🎯", "岗位清单", (a.jobs || []).map((x) => item(x.id, x.name,
    `${(x.time || "").slice(0, 16).replace("T", " ")} · ${(x.data || []).length} 个岗位`, false,
    [["pick", "选用"], ["del", "删除"]])));
  box.innerHTML = html || "<div class='empty-hint'>暂无生成文件版本 · 在对应板块生成后自动收录</div>";
}
function bindArtifactEvents2() {
  const box = $("artifactList");
  if (!box) return;
  box.onclick = (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    const sec = b.closest(".art-sec");
    const kind = sec ? sec.dataset.kind : "";
    const itemEl = b.closest(".art-item");
    const id = itemEl ? itemEl.dataset.id : "";
    if (act === "pick") {
      if (kind === "resume") setActiveResume(id);
      else if (kind === "materials") pickMaterial(id);
      else if (kind === "msrs") pickMsr(id);
      else if (kind === "jobs") pickJobs(id);
    } else if (act === "del") {
      if (kind === "resume") delResumeVersion(id);
      else delArtifact(kind, id);
    }
    renderArtifacts();
  };
}
function renderArtifacts() {
  renderArtifacts2();
  bindArtifactEvents2();
}

/* ================= CLI / MCP 工具管理（插件 = Agent 的工具） ================= */
let _tools = [];
let _editingToolId = null;
function renderTools() {
  const box = $("toolList");
  if (!box) return;
  box.innerHTML = _tools.map((t) => `
    <div class="tool-item">
      <label class="switch">
        <input type="checkbox" data-tid="${esc(t.id)}" ${t.enabled ? "checked" : ""}>
        <span class="slider"></span>
      </label>
      <div class="tool-info">
        <b>${esc(t.name)}</b><span class="tool-type ${t.type === "mcp" ? "mcp" : ""}">${t.type === "mcp" ? "MCP" : "CLI"}</span>
        ${t.preset ? '<span class="tool-preset">预置</span>' : ""}
        <em>${esc(t.desc || "")}</em>
        <code>${esc(t.command)}</code>
      </div>
      ${t.preset
        ? `<div class="tool-ops">
            <button class="btn-link" data-install="${esc(t.id)}">${t.installed ? "已配置 ✓" : "一键配置"}</button>
            <button class="btn-link btn-del-row" data-uninstall="${esc(t.id)}" ${t.installed ? "" : "disabled"}>一键卸载</button>
          </div>`
        : `<div class="tool-ops">
            <button class="btn-link" data-edit="${esc(t.id)}">编辑</button>
            <button class="btn-link btn-del-row" data-del="${esc(t.id)}">删除</button>
          </div>`}
    </div>`).join("") || "<div class='empty-hint'>暂无工具</div>";
  box.querySelectorAll("input[type=checkbox]").forEach((cb) => cb.addEventListener("change", async () => {
    await fetch(`/api/console/tool/${cb.dataset.tid}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: cb.checked }),
    });
    trkToast(cb.checked ? "已启用" : "已停用");
  }));
  box.querySelectorAll("[data-install]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("一键配置会安装该工具依赖，确认执行？")) return;
    b.disabled = true; b.textContent = "⏳ 配置中…";
    try {
      const r = await (await fetch(`/api/console/tool/${b.dataset.install}/install`, { method: "POST" })).json();
      if (r.ok) trkToast("已配置：依赖安装完成"); else trkToast("配置失败：" + (r.detail || ""), true);
    } catch (e) { trkToast("配置失败：" + e.message, true); }
    await reloadTools();
  }));
  box.querySelectorAll("[data-uninstall]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("一键卸载会移除该工具依赖并停用，确认执行？")) return;
    b.disabled = true; b.textContent = "⏳ 卸载中…";
    try {
      const r = await (await fetch(`/api/console/tool/${b.dataset.uninstall}/uninstall`, { method: "POST" })).json();
      if (r.ok) trkToast("已卸载"); else trkToast("卸载失败：" + (r.detail || ""), true);
    } catch (e) { trkToast("卸载失败：" + e.message, true); }
    await reloadTools();
  }));
  box.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => startEditTool(b.dataset.edit)));
  box.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm("确认删除该自定义工具？")) return;
    await fetch(`/api/console/tool/${b.dataset.del}`, { method: "DELETE" });
    await reloadTools();
    trkToast("已删除自定义工具");
  }));
}
async function reloadTools() {
  const d = await (await fetch("/api/console")).json();
  _tools = d.tools || [];
  renderTools();
}
function startEditTool(id) {
  const t = _tools.find((x) => x.id === id);
  if (!t) return;
  _editingToolId = id;
  $("toolName").value = t.name;
  $("toolType").value = t.type;
  $("toolCommand").value = t.command;
  $("toolDesc").value = t.desc || "";
  $("btnAddTool").textContent = "保存修改";
  $("btnCancelEditTool").classList.remove("hidden");
}
$("btnCancelEditTool").addEventListener("click", () => {
  _editingToolId = null;
  ["toolName", "toolType", "toolCommand", "toolDesc"].forEach((i) => { $("toolType") && $("toolType").value === "cli" ? null : null; });
  $("toolName").value = $("toolCommand").value = $("toolDesc").value = "";
  $("toolType").value = "cli";
  $("btnAddTool").textContent = "＋ 新增工具";
  $("btnCancelEditTool").classList.add("hidden");
  $("toolMsg").textContent = "";
});
$("btnAddTool").addEventListener("click", async () => {
  const body = { name: $("toolName").value.trim(), type: $("toolType").value, command: $("toolCommand").value.trim(), desc: $("toolDesc").value.trim() };
  if (!body.name || !body.command) { $("toolMsg").textContent = "工具名与命令不能为空"; return; }
  const isEdit = !!_editingToolId;
  const resp = await fetch(isEdit ? `/api/console/tool/${_editingToolId}` : "/api/console/tool", {
    method: isEdit ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const e = await resp.json().catch(() => ({}));
    $("toolMsg").textContent = e.detail || "保存失败";
    return;
  }
  $("toolMsg").textContent = isEdit ? "✓ 已保存修改" : "✓ 已新增工具";
  $("btnCancelEditTool").click();
  await reloadTools();
});

/* ================= 动态行：教育 / 项目 / 实习 / 岗位 ================= */
const ROW_TMPL = {
  edu: (v) => `<div class="row-grid">
      <input class="e-school" placeholder="学校" value="${esc(v.school)}">
      <input class="e-major" placeholder="专业" value="${esc(v.major)}">
      <select class="e-degree"><option value="本科">本科</option><option value="硕士">硕士</option><option value="博士">博士</option></select>
      <input class="e-year" placeholder="毕业年份，如 2026" value="${esc(v.year)}">
      <button class="btn-link btn-del-row">删除</button>
    </div>`,
  proj: (v) => `<div class="row-stack">
      <div class="row-grid">
        <input class="p-name" placeholder="项目名称" value="${esc(v.name)}">
        <input class="p-role" placeholder="角色，如 核心开发" value="${esc(v.role)}">
        <input class="p-time" placeholder="时间，如 2025.01-2025.04" value="${esc(v.time)}">
        <button class="btn-link btn-del-row">删除</button>
      </div>
      <input class="p-stack" placeholder="技术栈，逗号分隔" value="${esc(v.stack)}">
      <textarea class="p-desc" rows="2" placeholder="详细描述：做了什么、怎么做的、量化结果，越详细 AI 优化与岗位匹配越准">${esc(v.desc)}</textarea>
    </div>`,
  int: (v) => `<div class="row-stack">
      <div class="row-grid">
        <input class="i-company" placeholder="公司" value="${esc(v.company)}">
        <input class="i-position" placeholder="岗位，如 算法实习生" value="${esc(v.position)}">
        <input class="i-time" placeholder="时间，如 2025.06-2025.09" value="${esc(v.time)}">
        <button class="btn-link btn-del-row">删除</button>
      </div>
      <textarea class="i-desc" rows="2" placeholder="负责内容：项目、职责、成果，越详细越好">${esc(v.desc)}</textarea>
    </div>`,
  job: (v) => `<div class="row-stack">
      <div class="row-grid">
        <input class="j-title" placeholder="岗位标题" value="${esc(v.title)}">
        <input class="j-company" placeholder="公司" value="${esc(v.company)}">
        <button class="btn-link btn-del-row">删除</button>
      </div>
      <textarea class="j-jd" rows="2" placeholder="JD 要求，粘贴岗位描述越完整越准">${esc(v.jd)}</textarea>
    </div>`,
};
const EMPTY = { edu: {}, proj: {}, int: {}, job: {} };

function addRow(type) {
  const el = $(type === "edu" ? "eduRows" : type === "proj" ? "projRows" : type === "int" ? "intRows" : "jobRows");
  el.insertAdjacentHTML("beforeend", ROW_TMPL[type](EMPTY[type]));
  bindDel();
}
document.querySelectorAll("[data-add]").forEach((btn) => btn.addEventListener("click", () => addRow(btn.dataset.add)));
function bindDel() {
  document.querySelectorAll(".btn-del-row").forEach((b) => {
    b.onclick = () => b.closest(".row-grid, .row-stack").remove();
  });
}
// 初始各填充一行
["edu", "proj", "int", "job"].forEach(addRow);
document.querySelector("#projRows .p-desc").value = "用 LSTM 做车辆轨迹预测，vLLM 推理服务优化，预测精度提升 12%";
document.querySelector("#intRows .i-desc").value = "搭建向量检索链路，检索延迟降低 40%；优化召回准确率至 89%";
document.querySelector("#jobRows .j-jd").value = "要求掌握轨迹预测、python、深度学习";

/* ================= 画像收集（详细） ================= */
function collectProfile() {
  const edu = [...document.querySelectorAll("#eduRows .row-grid")].map((r) => ({
    school: r.querySelector(".e-school").value, major: r.querySelector(".e-major").value,
    degree: r.querySelector(".e-degree").value, year: r.querySelector(".e-year").value,
  })).filter((e) => e.school || e.major);
  const projects = [...document.querySelectorAll("#projRows .row-stack")].map((r) => ({
    name: r.querySelector(".p-name").value.trim(), role: r.querySelector(".p-role").value.trim(),
    time: r.querySelector(".p-time").value.trim(), stack: r.querySelector(".p-stack").value.trim(),
    desc: r.querySelector(".p-desc").value.trim(),
  })).filter((p) => p.desc || p.name);
  const internships = [...document.querySelectorAll("#intRows .row-stack")].map((r) => ({
    company: r.querySelector(".i-company").value.trim(), position: r.querySelector(".i-position").value.trim(),
    time: r.querySelector(".i-time").value.trim(), desc: r.querySelector(".i-desc").value.trim(),
  })).filter((i) => i.desc || i.company);
  return {
    name: $("inpName").value || "求职者",
    email: $("inpEmail").value.trim(),
    phone: $("inpPhone").value.trim(),
    website: $("inpWebsite").value.trim(),
    awards: $("inpAwards").value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
    education: edu,
    skills: $("inpSkills").value.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
    // 骨架消费字段：experience（项目在前）+ internship 独立段落透传
    experience: projects.map((p) => ({ name: p.name, role: p.role, time: p.time, stack: p.stack, desc: p.desc, type: "project" })),
    internships: internships.map((i) => ({ company: i.company, position: i.position, time: i.time, desc: i.desc, type: "internship" })),
    preference: { type: "fulltime", direction: $("inpDirection").value || "通用", city: $("inpCity").value || "不限" },
  };
}
function collectJobs() {
  return [...document.querySelectorAll("#jobRows .row-stack")].map((r) => ({
    title: r.querySelector(".j-title").value || "目标岗位",
    company: r.querySelector(".j-company").value || "",
    jd: r.querySelector(".j-jd").value || "",
  }));
}
function profileToText(p) {
  const parts = [`应届生，方向 ${p.preference?.direction || ""}`];
  (p.education || []).forEach((e) => parts.push(`教育：${e.school} ${e.major} ${e.degree} ${e.year}届`));
  if (p.skills?.length) parts.push(`技能：${p.skills.join("、")}`);
  if (p.awards?.length) parts.push(`奖项：${p.awards.join("、")}`);
  (p.experience || []).forEach((e) => parts.push(`项目${e.name ? `「${e.name}」` : ""}：${e.desc}`));
  (p.internships || []).forEach((i) => {
    const org = [i.company, i.position].filter(Boolean).join("·");
    parts.push(`实习/工作${org ? `「${org}」` : ""}：${i.desc}`);
  });
  return parts.join("\n");
}
function autoFillProfileText() {
  const ver = activeResume();
  const text = ver ? ver.text : profileToText(collectProfile());
  $("inpProfileText").value = text;
  renderDirectionChips(text);
}

/* ================= 简历版本管理（localStorage，字母 A-Z 自动编号） ================= */
const RESUME_KEY = "jobhunter_resumes";
const ACTIVE_RESUME_KEY = "jobhunter_active_resume";

function resumeVersions() { try { return JSON.parse(localStorage.getItem(RESUME_KEY) || "[]"); } catch { return []; } }
function saveResumeVersions(list) { localStorage.setItem(RESUME_KEY, JSON.stringify(list)); }
function activeResume() {
  const id = localStorage.getItem(ACTIVE_RESUME_KEY);
  return resumeVersions().find((v) => v.id === id) || null;
}
function nextLetter(list) {
  const used = new Set(list.map((v) => v.letter));
  for (let i = 0; i < 26; i++) {
    const L = String.fromCharCode(65 + i);
    if (!used.has(L)) return L;
  }
  return "?";
}
function addResumeVersion(name, text, source) {
  const list = resumeVersions();
  const v = { id: Date.now().toString(36), letter: nextLetter(list), name, source, text, updatedAt: new Date().toISOString() };
  list.push(v);
  saveResumeVersions(list);
  localStorage.setItem(ACTIVE_RESUME_KEY, v.id);
  refreshResumeUI();
  return v;
}
function delResumeVersion(id) {
  saveResumeVersions(resumeVersions().filter((v) => v.id !== id));
  if (localStorage.getItem(ACTIVE_RESUME_KEY) === id) localStorage.removeItem(ACTIVE_RESUME_KEY);
  refreshResumeUI();
}
function setActiveResume(id) { localStorage.setItem(ACTIVE_RESUME_KEY, id); refreshResumeUI(); }
function refreshResumeUI() {
  if ($("resumeVers")) renderResumeVers();
  if ($("railResume")) renderResumeManage();
  renderVersionOptions($("inpResumeVer"));
  renderVersionOptions($("inpIntVer"));
}
function renderResumeVers() {
  const box = $("resumeVers");
  if (!box) return;
  const list = resumeVersions();
  const activeId = localStorage.getItem(ACTIVE_RESUME_KEY);
  box.innerHTML = list.map((v) => `
    <div class="ver-item ${v.id === activeId ? "active" : ""}">
      <span class="ver-letter">${v.letter}</span>
      <div class="ver-info"><b>${esc(v.name)}</b>
        <em>${v.source === "upload" ? "上传 / 粘贴" : "表单生成"} · ${(v.text || "").length} 字 · ${esc((v.updatedAt || "").slice(0, 10))}</em>
      </div>
      <button class="btn-link ver-pick" data-pick="${v.id}">${v.id === activeId ? "✓ 使用中" : "选用"}</button>
      <button class="btn-link btn-del-row" data-del="${v.id}">删除</button>
    </div>`).join("")
    || `<div class="empty-hint">还没有简历版本。生成简历后自动保存为「表单版」，或上传 txt/md。</div>`;
  document.querySelectorAll("#resumeVers [data-pick]").forEach((b) => b.addEventListener("click", () => setActiveResume(b.dataset.pick)));
  document.querySelectorAll("#resumeVers [data-del]").forEach((b) => b.addEventListener("click", () => delResumeVersion(b.dataset.del)));
  renderVersionOptions($("inpResumeVer"));
  renderVersionOptions($("inpIntVer"));
}
function renderVersionOptions(sel) {
  if (!sel) return;
  const list = resumeVersions();
  const activeId = localStorage.getItem(ACTIVE_RESUME_KEY);
  sel.innerHTML = '<option value="">未选择版本</option>' + list.map((v) =>
    `<option value="${v.id}" ${v.id === activeId ? "selected" : ""}>${v.letter} · ${esc(v.name)}</option>`).join("");
}
function resumeTextOf(id) {
  const v = resumeVersions().find((x) => x.id === id);
  return v ? v.text : "";
}

/* ================= 匹配方向推荐（基于技能关键词打分 top5） ================= */
const DIR_RULES = {
  "大模型应用": ["llm", "大模型", "langchain", "rag", "agent", "prompt", "vllm", "向量检索", "微调", "推理", "知识库"],
  "机器学习 / 算法": ["机器学习", "深度学习", "pytorch", "tensorflow", "cnn", "lstm", "transformer", "回归", "分类", "神经网络", "numpy"],
  "后端开发": ["java", "go", "golang", "spring", "mysql", "redis", "微服务", "django", "flask", "fastapi", "linux"],
  "数据科学 / 分析": ["pandas", "numpy", "sql", "hive", "spark", "统计", "数据挖掘", "可视化", "建模", "ab test", "数据分析"],
  "前端开发": ["react", "vue", "typescript", "html", "css", "javascript", "前端"],
  "测试 / 质量": ["pytest", "自动化测试", "测试", "质量保障", "selenium", "mock"],
  "云计算 / 运维": ["docker", "kubernetes", "k8s", "ci/cd", "devops", "监控", "部署"],
  "计算机视觉": ["opencv", "目标检测", "图像", "yolo", "视觉", "分割", "检测"],
  "自然语言处理": ["nlp", "分词", "情感分析", "文本", "词向量", "bert", "gpt"],
  "推荐系统": ["推荐", "协同过滤", "召回", "排序", "ctr"],
  "数据挖掘 / 风控": ["风控", "反欺诈", "特征工程", "埋点", "规则"],
};
function recommendDirections(text) {
  const low = String(text || "").toLowerCase();
  return Object.entries(DIR_RULES)
    .map(([dir, kws]) => ({ dir, score: kws.filter((k) => low.includes(k.toLowerCase())).length }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.dir.localeCompare(b.dir, "zh"))
    .slice(0, 5);
}
/* 类别 → 具体岗位名：推荐展示 5 个不同的岗位 */
const DIR_POSITION = {
  "大模型应用": "大模型应用开发工程师",
  "机器学习 / 算法": "机器学习算法工程师",
  "后端开发": "后端开发工程师",
  "数据科学 / 分析": "数据分析师",
  "前端开发": "前端开发工程师",
  "测试 / 质量": "测试开发工程师",
  "云计算 / 运维": "云运维开发工程师",
  "计算机视觉": "计算机视觉算法工程师",
  "自然语言处理": "NLP 算法工程师",
  "推荐系统": "推荐算法工程师",
  "数据挖掘 / 风控": "数据挖掘工程师",
};
function renderDirectionChips(text) {
  const box = $("directionChips");
  const recs = recommendDirections(text).map((r) => ({ dir: r.dir, pos: DIR_POSITION[r.dir] || r.dir }));
  box.innerHTML = recs.length
    ? recs.map((c) => `<span class="chip" data-dir="${esc(c.dir)}">${esc(c.pos)}</span>`).join("")
    : '<span class="muted small">暂无推荐，画像越详细越准</span>';
  document.querySelectorAll("#directionChips .chip").forEach((c) =>
    c.addEventListener("click", () => {
      const pos = DIR_POSITION[c.dataset.dir] || c.dataset.dir;
      const ta = $("inpProfileText");
      ta.value = "求职方向：" + pos + "\n" + ta.value.replace(/^求职方向：.*\n?/, "");
      document.querySelectorAll("#directionChips .chip").forEach((x) => x.classList.remove("active"));
      c.classList.add("active");
    }));
}
$("inpResumeVer").addEventListener("change", () => {
  const t = resumeTextOf($("inpResumeVer").value);
  if (t) { $("inpProfileText").value = t; renderDirectionChips(t); }
});

/* ================= 岗位清单 CSV 导出（Excel 直接打开） ================= */
function exportJobsCsv(jobs) {
  const head = ["岗位", "公司", "城市", "薪资", "匹配度", "来源", "技能", "要求", "链接"];
  const rows = jobs.map((j) => [
    j.title || j.job_title || "", j.company || "", j.city || "", j.salary || "面议",
    j.match_score ?? j.final_score ?? 0, j.source || "", (j.skills || []).join(" "),
    j.education ? `${j.education} ${j.experience || ""}`.trim() : "", j.url || "",
  ]);
  const csv = "\uFEFF" + [head, ...rows].map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = "jobhunter-jobs-" + new Date().toISOString().slice(0, 10) + ".csv";
  a.click();
  URL.revokeObjectURL(a.href);
}
$("btnExportCsv").addEventListener("click", () => exportJobsCsv(window._lastJobs || []));

/* ================= 简历生成 → A4 预览 ================= */
const PHOTO_KEY = "jobhunter_photo";
/* 证件照：本地压缩为 base64 存 localStorage，不落服务器 */
$("inpPhoto").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const bmp = await createImageBitmap(f);
    const scale = Math.min(1, 320 / bmp.width);
    const cv = document.createElement("canvas");
    cv.width = Math.max(1, Math.round(bmp.width * scale));
    cv.height = Math.max(1, Math.round(bmp.height * scale));
    cv.getContext("2d").drawImage(bmp, 0, 0, cv.width, cv.height);
    localStorage.setItem(PHOTO_KEY, cv.toDataURL("image/jpeg", 0.85));
    $("photoHint").textContent = "已上传 ✓（可在预览中查看右上角）";
    $("btnPhotoClear").classList.remove("hidden");
    if (window._runData) renderSheet(window._runData);
  } catch (err) {
    $("photoHint").textContent = "读取图片失败：" + err.message;
  }
});
$("btnPhotoClear").addEventListener("click", () => {
  localStorage.removeItem(PHOTO_KEY);
  $("inpPhoto").value = "";
  $("photoHint").textContent = "选填，将显示在简历右上角（约 2.3cm × 3cm）";
  $("btnPhotoClear").classList.add("hidden");
  if (window._runData) renderSheet(window._runData);
});
/* 页数切换：已有预览则即时按新页数重排 */
$("inpResumePages").addEventListener("change", () => { if (window._runData) renderSheet(window._runData); });

$("btnGenResume").addEventListener("click", async () => {
  $("genStatus").textContent = "生成中…";
  try {
    const p = collectProfile();
    const data = await apiRun({
      profile: p,
      target_jobs: collectJobs(),
      user_goal: "帮我找工作",
      submission_input: { city: p.preference?.city || "", max_results: 10, company_types: [] },
    });
    window._runData = data;
    renderSheet(window._runData);
    // 自动把表单画像保存为「表单版」简历版本（同名去重更新）
    const list = resumeVersions();
    const exist = list.find((v) => v.source === "form" && v.name.startsWith(p.name));
    if (exist) {
      exist.text = profileToText(p);
      exist.updatedAt = new Date().toISOString();
      saveResumeVersions(list);
    } else {
      addResumeVersion(p.name + " 表单版", profileToText(p), "form");
    }
    renderResumeVers();
    $("genStatus").textContent = verdictText(window._runData);
    $("btnExportPdf").classList.remove("hidden");
    $("resumeEmpty").classList.add("hidden");
    $("resumeWrap").classList.remove("hidden");
  } catch (e) {
    $("genStatus").textContent = "生成失败：" + e.message;
  }
});

function verdictText(d) {
  const map = {
    pass: "✓ 你的简历和岗位方向很匹配，可以直接投递",
    accept_with_issues: "整体达标，按建议再优化一下会更好",
    fail: "匹配度还没到位，先按建议优化简历再投",
  };
  return map[d.gate_verdict] || "简历已生成";
}

function renderSheet(d) {
  const r = d.resume || {};
  const sheet = $("resumeSheet");
  // 优先渲染 resume_agent 模板 html（专业 ATS 版式：单栏/量化/STAR/高密度）；
  // 无 html（组件降级/旧数据）时回退表单回显版
  if (r.html && String(r.html).trim()) {
    sheet.className = "sheet sheet-html";
    sheet.innerHTML = `<iframe class="resume-frame" srcdoc="${esc(r.html)}" title="简历预览" onload="resumeFrameAutoHeight(this)"></iframe>`;
    return;
  }
  const p = collectProfile();
  const onePage = $("inpResumePages").value === "1";
  const photo = localStorage.getItem(PHOTO_KEY) || "";
  // summary 兼容两种形态：mock 返回字符串，real 可能返回 [{text}] 数组
  const summary = Array.isArray(r.summary)
    ? r.summary.map((s) => s.text || "").join(" ").trim()
    : String(r.summary || "").trim();
  const eduHtml = p.education.map((e) =>
    `<div class="row-line"><b>${esc(e.school)}</b><span>${esc(e.major)} · ${esc(e.degree)} · ${esc(e.year)}届</span></div>`).join("")
    || `<div class="row-line muted">未填写教育经历</div>`;
  const projHtml = p.experience.map((e) => {
    const meta = [e.role, e.time].filter(Boolean).join(" · ");
    return `
    <div class="row-line"><b>${esc(headOf(e.name, e.desc))}</b>${meta ? `<span>${esc(meta)}</span>` : ""}</div>
    <div class="row-sub">${esc(e.desc)}${e.stack ? `<br><span class="muted">技术栈：${esc(e.stack)}</span>` : ""}</div>`;
  }).join("")
    || `<div class="row-line muted">未填写项目经历</div>`;
  const intHtml = p.internships.map((i) => {
    const meta = [i.position, i.time].filter(Boolean).join(" · ");
    return `
    <div class="row-line"><b>${esc(headOf(i.company, i.desc))}</b>${meta ? `<span>${esc(meta)}</span>` : ""}</div>
    <div class="row-sub">${esc(i.desc)}</div>`;
  }).join("")
    || `<div class="row-line muted">未填写实习/工作经历</div>`;
  const contact = [p.email && `邮箱 ${p.email}`, p.phone && `电话 ${p.phone}`, p.website && `主页 ${p.website}`].filter(Boolean).join(" · ");
  // 1 页精简版：省略奖项荣誉（排版密度由 .sheet-p1 样式压缩）
  const awardHtml = onePage ? "" : (p.awards || []).map((a) => `<div class="row-line">${esc(a)}</div>`).join("");
  sheet.className = "sheet" + (onePage ? " sheet-p1" : "");
  sheet.innerHTML = `
    <div class="sheet-head">
      <div class="sheet-main">
        <h1>${esc(p.name)}</h1>
        <div class="sheet-dir">${esc(p.preference.direction)} · 期望城市 ${esc(p.preference.city)}</div>
        ${contact ? `<div class="sheet-contact">${esc(contact)}</div>` : ""}
      </div>
      ${photo ? `<div class="sheet-photo"><img src="${photo}" alt="证件照"></div>` : ""}
    </div>
    ${summary ? `<div class="sheet-sec"><h3>个人简介</h3><p>${esc(summary)}</p></div>` : ""}
    <div class="sheet-sec"><h3>教育经历</h3>${eduHtml}</div>
    <div class="sheet-sec"><h3>项目经历</h3>${projHtml}</div>
    <div class="sheet-sec"><h3>实习/工作经历</h3>${intHtml}</div>
    ${awardHtml ? `<div class="sheet-sec"><h3>奖项荣誉</h3>${awardHtml}</div>` : ""}
    <div class="sheet-sec"><h3>技能</h3><div class="sheet-skills">${esc(p.skills.join(" · "))}</div></div>`;
}

/* 简历 iframe 高度自适应：按内容实际高度撑开（srcdoc 同源可直接读 body） */
function resumeFrameAutoHeight(f) {
  try {
    const doc = f.contentDocument || f.contentWindow.document;
    f.style.height = (doc.body.scrollHeight + 24) + "px";
  } catch (e) { /* 加载中/跨域忽略，保持默认高度 */ }
}

/* 导出 PDF：只打印简历纸面 */
$("btnExportPdf").addEventListener("click", () => window.print());

/* ================= 板块 B：岗位匹配 ================= */
$("btnMatch").addEventListener("click", async () => {
  $("matchMeta").textContent = "正在搜索…";
  try {
    const resp = await fetch("/api/match", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_text: $("inpProfileText").value, city: $("inpMatchCity").value || $("inpCity").value, max_results: parseInt($("inpMaxResults").value, 10) }),
    });
    const _body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(_body.detail || `HTTP ${resp.status}`);
    let data = _body;
    if (data.status !== "done") data = await pollMatch(data.job_id);
    const jobs = data.jobs || [];
    $("matchMeta").textContent = `共 ${jobs.length} 个岗位 · ${data.channel || "搜索通道"}`;
    window._lastJobs = jobs;
    $("btnExportCsv").classList.remove("hidden");
    saveArtifact("jobs", `岗位清单 ${jobs.length} 个 · ${data.channel || "搜索"}`, jobs);
    renderJobs(jobs);
  } catch (e) {
    $("matchMeta").textContent = "匹配失败：" + e.message;
  }
});
async function pollMatch(jobId) {
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const d = await (await fetch(`/api/match/${jobId}`)).json();
    if (d.status === "done" || d.done) return d;
    if (d.status === "failed") throw new Error(d.error || "匹配失败");
  }
  throw new Error("匹配超时");
}

function renderJobs(jobs) {
  $("jobsEmpty").classList.add("hidden");
  $("jobsList").innerHTML = jobs.map((j, i) => {
    const score = Number(j.match_score ?? j.final_score ?? 0);
    return `
    <div class="job-card">
      <div class="job-main">
        <div class="job-score">
          <div class="score-ring" style="--p:${score}"><span>${score}</span></div>
          <div class="score-label">匹配度</div>
        </div>
        <div class="job-info">
          <div class="job-title-line"><b>${esc(j.title || j.job_title || "岗位")}</b>
            <span class="pill ${score >= 80 ? "pill-pass" : score >= 60 ? "pill-warn" : "pill-muted"}">${score >= 80 ? "很匹配" : score >= 60 ? "可考虑" : "需提升"}</span>
          </div>
          <div class="job-meta">${esc(j.company || "")} · ${esc(j.city || "")} · ${esc(j.salary || "薪资面议")} · ${esc(j.industry || "")}</div>
          <div class="job-tags">${(j.skills || []).map((s) => `<span class="tag">${esc(s)}</span>`).join("")}</div>
        </div>
        <div class="job-actions">
          <button class="btn btn-ghost btn-sm btn-save" data-i="${i}">${isSaved(j) ? "已收藏 ✓" : "收藏"}</button>
          <button class="btn btn-link btn-sm btn-detail" data-i="${i}">详情 ∨</button>
        </div>
      </div>
      <div class="job-detail hidden">
        <div class="kv-item"><span class="k">相关链接</span><span class="v">${esc(j.link || j.url || j.source_url || "暂无")}</span></div>
        <div class="kv-item"><span class="k">要求</span><span class="v">${esc(j.education || "-")} · 经验 ${esc(j.experience || j.experience_years || "不限")}</span></div>
      </div>
    </div>`;
  }).join("") || "<div class='empty-hint'>没有找到匹配岗位，试试换个城市或方向</div>";
  document.querySelectorAll("#jobsList .btn-detail").forEach((b) => b.addEventListener("click", () => {
    const d = b.closest(".job-card").querySelector(".job-detail");
    d.classList.toggle("hidden");
    b.textContent = d.classList.contains("hidden") ? "详情 ∨" : "收起 ∧";
  }));
  document.querySelectorAll("#jobsList .btn-save").forEach((b) => b.addEventListener("click", () => {
    toggleSave(jobs[b.dataset.i]);
    b.textContent = isSaved(jobs[b.dataset.i]) ? "已收藏 ✓" : "收藏";
    renderSaved();
  }));
}

/* ================= 收藏（localStorage） ================= */
function savedJobs() { try { return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]"); } catch { return []; } }
function isSaved(j) { return savedJobs().some((s) => s.title === j.title && s.company === j.company); }
function toggleSave(j) {
  const list = savedJobs();
  const idx = list.findIndex((s) => s.title === j.title && s.company === j.company);
  if (idx >= 0) list.splice(idx, 1);
  else list.push({ title: j.title, company: j.company, city: j.city, salary: j.salary, score: j.match_score ?? j.final_score ?? 0 });
  localStorage.setItem(SAVED_KEY, JSON.stringify(list));
}
function renderSaved() {
  const list = savedJobs();
  $("savedList").innerHTML = list.map((s, i) => `
    <div class="job-card compact">
      <div class="job-info">
        <div class="job-title-line"><b>${esc(s.title)}</b><span class="pill pill-pass">${s.score} 分</span></div>
        <div class="job-meta">${esc(s.company)} · ${esc(s.city)} · ${esc(s.salary)}</div>
      </div>
      <div class="job-actions">
        <button class="btn-link btn-del-row" data-unsave="${i}">取消收藏</button>
      </div>
    </div>`).join("") || "<div class='empty-hint'>还没有收藏岗位。</div>";
  document.querySelectorAll("#savedList [data-unsave]").forEach((b) => b.addEventListener("click", () => {
    const list2 = savedJobs();
    const s = list2[b.dataset.unsave];
    if (!s) return;
    if (confirm(`确认取消收藏「${s.title} · ${s.company}」？`)) {
      toggleSave(s);
      renderSaved();
    }
  }));
}

/* ================= 板块 C：面试准备 ================= */
$("btnGenMaterials").addEventListener("click", async () => {
  $("matStatus").textContent = "生成中…";
  try {
    const jd = $("inpIntJd").value.trim();
    const extra = $("inpIntExtra").value.trim();
    const verText = resumeTextOf($("inpIntVer").value);
    const profile = collectProfile();
    // 版本文本随画像透传（骨架节点可读），意向 JD + 面经链接并入 target_jobs 供面试材料节点消费
    const data = await apiRun({
      profile: { ...profile, text: verText || profileToText(profile) },
      target_jobs: [
        // 用户显式填写的意向 JD 优先（节点消费 target_jobs[0]），示例岗位行仅作补充
        ...(jd ? [{ title: "意向岗位", jd: extra ? `${jd}\n\n补充信息：\n${extra}` : jd }] : []),
        ...collectJobs(),
      ],
      user_goal: "准备面试",
      // 面试材料流程跳过 N9 简历确认（已在简历生成流程确认过，重复弹窗仅徒增等待）
      config: { skip_confirm: true },
    });
    window._runData = data;
    renderInterviewCached();
    $("matStatus").textContent = "✓ 已生成，可在下方预览或导出 HTML";
    saveArtifact("materials", `面试材料 · ${(window._runData.interview_materials || {}).title || "意向岗位"}`, window._runData.interview_materials || {});
    saveArtifact("msrs", `复盘报告 · ${(window._runData.msr_report || {}).source || "未知来源"}`, window._runData.msr_report || {});
  } catch (e) { $("matStatus").textContent = "生成失败：" + e.message; }
});
/* 导出面试材料 HTML：自动命名「姓名-岗位-面试材料.html」 */
function exportMaterialsHtml() {
  const m = (window._runData || {}).interview_materials || {};
  if (!m.html) return;
  const profile = collectProfile();
  const name = (profile.name || "求职者").trim();
  const jobTitle = [m.title, collectJobs().map((j) => j.title).find(Boolean), profile.preference?.direction]
    .find((v) => v && v !== "意向岗位");
  const sanitize = (s) => String(s || "求职").replace(/[\\/:*?"<>|\n]/g, " ").trim();
  const blob = new Blob([m.html], { type: "text/html;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${sanitize(name)}-${sanitize(jobTitle)}-面试材料.html`;
  a.click();
  URL.revokeObjectURL(a.href);
  trkToast("已导出面试材料 HTML");
}
$("btnExportMaterials").addEventListener("click", exportMaterialsHtml);
function renderInterviewCached() {
  const d = window._runData;
  // 切板块返回时 _runData 可能被其他板块覆盖：从生成文件版本恢复最近一次材料
  const m = ((d || {}).interview_materials) || (() => {
    const arts = getArtifacts().materials || [];
    return arts.length ? (arts[arts.length - 1].data || {}) : {};
  })();
  const msr = ((d || {}).msr_report) || {};
  if (m.html) {
    // 浏览器内预览渲染效果（非代码）：iframe srcdoc 呈现完整 HTML
    $("matPreview").innerHTML = `<iframe class="mat-frame" srcdoc="${esc(m.html)}" title="面试材料预览"></iframe>`;
    $("btnExportMaterials").classList.remove("hidden");
  } else {
    $("matPreview").innerHTML = "<div class='empty-hint'>先点击上方「生成面试材料」，生成后可在此预览效果并导出 HTML。</div>";
    $("btnExportMaterials").classList.add("hidden");
  }
  const rows = [
    ["复盘来源", msr.source || "-"],
    ["公司", msr.company || "-"],
    ["薄弱点", (msr.analysis?.weak_points || []).join("、") || "-"],
    ["改进建议", (msr.analysis?.improve || []).join("；") || "-"],
  ];
  $("msrView").innerHTML = kvHtml(rows);
}

/* ================= 面试复盘：一键总结 → 面试经验.md ================= */
const MSR_MD_KEY = "jobhunter_interview_exp";
function msrMarkdown() {
  const note = $("inpMsrNote").value.trim();
  const msr = (window._runData || {}).msr_report || {};
  const lines = [];
  lines.push("# 面试经验");
  lines.push("");
  lines.push(`> ${msr.source ? `复盘来源：${msr.source}` : "手动记录"} · ${new Date().toLocaleDateString()}`);
  lines.push("");
  if ((msr.analysis?.weak_points || []).length) lines.push("## 薄弱点", ...msr.analysis.weak_points.map((x) => "- " + x), "");
  if ((msr.analysis?.improve || []).length) lines.push("## 改进建议", ...msr.analysis.improve.map((x) => "- " + x), "");
  if (note) lines.push("## 复盘记录", note, "");
  return lines.join("\n").trim() + "\n";
}
function openMsrView() {
  $("msrMdView").textContent = localStorage.getItem(MSR_MD_KEY) || msrMarkdown();
  $("msrModalMask").classList.remove("hidden");
}
function exportMsrMd() {
  const md = localStorage.getItem(MSR_MD_KEY) || msrMarkdown();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([md], { type: "text/markdown;charset=utf-8" }));
  a.download = "面试经验.md";
  a.click();
  URL.revokeObjectURL(a.href);
}
$("btnMsrSummarize").addEventListener("click", () => {
  if (!$("inpMsrNote").value.trim()) { trkToast("请先输入复盘内容", true); return; }
  localStorage.setItem(MSR_MD_KEY, msrMarkdown());
  trkToast("已总结进 面试经验.md");
});
$("btnMsrView").addEventListener("click", openMsrView);
$("btnMsrExport").addEventListener("click", exportMsrMd);
$("btnMsrExportModal").addEventListener("click", exportMsrMd);
$("btnCloseMsr").addEventListener("click", () => $("msrModalMask").classList.add("hidden"));
$("msrModalMask").addEventListener("click", (e) => { if (e.target === $("msrModalMask")) $("msrModalMask").classList.add("hidden"); });

/* ================= 板块 D：面试跟踪（复现 interview-tracker 子项目界面与逻辑规则） ================= */
const TRK_DATA_KEY = "jobhunter_tracker_data";
const trkState = {
  companies: [], jobs: [],
  filter: { tab: "all", kw: "", status: "", city: "", workType: "" },
  editingJobId: null, aiDraft: null, modalMode: "form", aiOnline: false, aiForceCat: false,
};
const WORK_TYPE_LABEL = { autumn: "秋招", convert: "有转正实习", nonconvert: "日常实习", unknown: "未知" };
const RESULT_LABEL = { offer: "Offer", fail: "挂", giveup: "放弃" };
const CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"];
const STAGE_LABELS = { resume: "简历筛选", written: "笔试", hr: "HR面" };
/* 流程深度权重（饱和：越深加分越缓） */
const DEPTH_SCORE = { resume: 0.2, written: 0.35, hr: 1.0 };

/* ---------- 数据持久化（localStorage；旧 jobhunter_tracks 一次性迁移） ---------- */
function trkLoadData() {
  try {
    const d = JSON.parse(localStorage.getItem(TRK_DATA_KEY) || "null");
    trkState.companies = (d && d.companies) || [];
    trkState.jobs = (d && d.jobs) || [];
  } catch { trkState.companies = []; trkState.jobs = []; }
  if (trkState.jobs.length === 0) {
    try {
      const old = JSON.parse(localStorage.getItem(TRACK_KEY) || "[]");
      old.forEach((t) => {
        let c = trkState.companies.find((x) => x.name === t.company);
        if (!c) { c = { id: trkNewId(), name: t.company || "未知公司", pinnedAt: null, note: "" }; trkState.companies.push(c); }
        trkState.jobs.push({
          id: trkNewId(), companyId: c.id, title: t.job || "岗位名称待补充", workType: "unknown",
          city: t.city || "", url: "", appliedDate: trkLocalToday(), interviewAt: null, note: t.note || "",
          todo: null, offerDeadline: null,
          stages: { resume: { date: "", state: null }, written: { date: "", state: null, deadline: null }, interviews: [], hr: null },
          result: t.status === "结束" ? "fail" : null, updatedAt: trkNowIso(), pinnedAt: null,
        });
      });
      if (old.length) { trkSaveData(); localStorage.removeItem(TRACK_KEY); }
    } catch { /* 迁移失败忽略 */ }
  }
}
function trkSaveData() {
  localStorage.setItem(TRK_DATA_KEY, JSON.stringify({ companies: trkState.companies, jobs: trkState.jobs }));
}

/* ---------- 工具 ---------- */
function trkNowIso() { return new Date().toISOString(); }
function trkNewId() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function trkLocalToday() { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
function trkFormatDate(v) { return v ? String(v).slice(0, 10) : ""; }
function trkLocalMidnight(ds) { const t = new Date(String(ds).slice(0, 10) + "T00:00:00").getTime(); return isNaN(t) ? 0 : t; }
function trkFmtDateTime(ts) {
  const d = new Date(ts); if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
}
function trkLocalIvStr(ts) {
  if (!ts) return "";
  const s = String(ts);
  if (/Z$|[+-]\d{2}:?\d{2}$/.test(s)) {
    const d = new Date(s);
    if (!isNaN(d.getTime())) {
      const p = (n) => String(n).padStart(2, "0");
      return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
    }
  }
  return s.slice(0, 16).replace("T", " ");
}
function trkCompanyOf(job) { return trkState.companies.find((c) => c.id === job.companyId); }
function trkJobCities(job) { return String(job.city || "").split(/[\/、,，;；|]/).map((s) => s.trim()).filter(Boolean); }

/* ---------- 流程环节模型（固定骨架 + 动态面试轮；渲染/排序/提醒共用） ---------- */
function stageList(job) {
  const s = job.stages || {};
  const list = [];
  for (const k of ["resume", "written"]) { if (s[k]) list.push({ key: k, label: STAGE_LABELS[k], v: s[k] }); }
  (s.interviews || []).forEach((v, i) => list.push({ key: "iv" + i, label: (CN_NUM[i] || String(i + 1)) + "面", v: v || { date: "", state: null } }));
  if (s.hr) list.push({ key: "hr", label: STAGE_LABELS.hr, v: s.hr });
  return list;
}
function pipelineDepth(job) {
  const s = job.stages || {};
  let depth = 0;
  for (const [k, base] of Object.entries(DEPTH_SCORE)) {
    const v = s[k];
    if (v && v.state === "pass") depth = Math.max(depth, base);
  }
  return depth;
}

/* ---------- 进度分组 / 状态判定（对齐子项目） ---------- */
function jobGroup(job) {
  if (job.result === "offer") return 3;
  if (job.result === "fail" || job.result === "giveup") return 2;
  const steps = stageList(job);
  const act = steps.filter((x) => x.v && x.v.state && x.v.state !== "skip");
  if (act.length === 0 && !job.interviewAt) return 0;
  if (act.some((x) => x.v.state === "fail")) return 2;
  const first = act[0];
  if (first && first.key === "resume" && first.v.state === "wait" && act.length === 1 && !job.interviewAt) return 0;
  return 1;
}
const GROUP_LABEL = { 0: "已投待进展", 1: "进行中", 2: "已挂 / 放弃", 3: "Offer" };
function allStagesPassed(job) {
  const steps = stageList(job);
  const hasPass = steps.some((x) => x.v.state === "pass");
  if (!hasPass) return false;
  if (steps.some((x) => x.v.state === "wait" || x.v.state === "todo" || x.v.state === "fail")) return false;
  const lastPassIdx = steps.map((x) => x.v.state).lastIndexOf("pass");
  for (let i = lastPassIdx + 1; i < steps.length; i++) {
    const st = steps[i].v.state;
    if (st !== "pass" && st !== "skip") return false;
  }
  return true;
}
function interviewSettled(job) {
  const ivs = (job.stages || {}).interviews || [];
  const last = ivs[ivs.length - 1];
  return !!last && (last.state === "pass" || last.state === "fail" || last.state === "wait");
}
function hasFutureInterview(job) {
  if (!job.interviewAt) return false;
  if (interviewSettled(job)) return false;
  const t = new Date(job.interviewAt).getTime();
  return !isNaN(t) && t > Date.now();
}
function writtenDeadlineTs(job) {
  const w = (job.stages || {}).written;
  if (!w || !w.deadline) return 0;
  if (w.state === "pass" || w.state === "fail" || w.state === "wait") return 0;
  const t = new Date(w.deadline).getTime();
  return !isNaN(t) ? t : 0;
}
function urgentWrittenDeadline(job) {
  const t = writtenDeadlineTs(job);
  if (!t) return false;
  const diff = t - Date.now();
  return diff > 0 && diff <= 48 * 3600 * 1000;
}
function urgentIn24h(job) {
  if (!job.interviewAt) return false;
  if (interviewSettled(job)) return false;
  const t = new Date(job.interviewAt).getTime();
  if (!t || isNaN(t)) return false;
  const diff = t - Date.now();
  return diff > 0 && diff <= 24 * 3600 * 1000;
}
function offerPending(job) { return job.result === "offer"; }

/* ---------- 优先级评分 + 排序分层（面试→笔试DDL→Offer→置顶→常规→终态） ---------- */
function priorityScore(job) {
  const depth = pipelineDepth(job);
  const hasWait = stageList(job).some((x) => x.v.state === "wait" || x.v.state === "todo");
  let recency = 0;
  if (job.updatedAt) {
    const hours = (Date.now() - new Date(job.updatedAt).getTime()) / 3600000;
    recency = Math.exp(-hours / (24 * 7));
  }
  return depth * 0.6 + recency * 0.4 + (hasWait ? 0.15 : 0) + (job.workType === "convert" ? 0.1 : 0);
}
function sortGroup(job) {
  if (offerPending(job)) return 1.5;
  if (job.result === "fail" || job.result === "giveup") return 4;
  if (hasFutureInterview(job)) return 0;
  if (urgentWrittenDeadline(job)) return 1;
  if (job.pinnedAt) return 2;
  return 3;
}
function sortJobs(jobs) {
  return [...jobs].sort((a, b) => {
    const ga = sortGroup(a), gb = sortGroup(b);
    if (ga !== gb) return ga - gb;
    if (ga === 0) return new Date(a.interviewAt).getTime() - new Date(b.interviewAt).getTime();
    if (ga === 1) return writtenDeadlineTs(a) - writtenDeadlineTs(b);
    if (ga === 1.5) return trkLocalMidnight(a.offerDeadline) - trkLocalMidnight(b.offerDeadline);
    if (ga === 2) return String(a.pinnedAt).localeCompare(String(b.pinnedAt));
    if (ga === 3) return priorityScore(b) - priorityScore(a);
    return String(b.updatedAt || "").localeCompare(String(a.updatedAt || ""));
  });
}

/* ---------- 过滤 ---------- */
function filteredJobs() {
  const f = trkState.filter;
  return trkState.jobs.filter((job) => {
    if (f.tab === "offer") { if (job.result !== "offer") return false; }
    else if (f.tab === "autumn") { if (job.workType !== "autumn") return false; }
    else if (f.tab === "intern") { if (job.workType === "autumn") return false; }
    if (f.status !== "" && String(jobGroup(job)) !== f.status) return false;
    if (f.city && !trkJobCities(job).includes(f.city)) return false;
    if (f.workType && job.workType !== f.workType) return false;
    if (f.kw) {
      const c = trkCompanyOf(job);
      const hay = (job.title || "") + " " + (c ? c.name : "");
      if (!hay.toLowerCase().includes(f.kw.toLowerCase())) return false;
    }
    return true;
  });
}

/* ---------- 流程环节渲染（chip 流） ---------- */
function flowStepHtml(label, v) {
  if (!v || !v.state) return '<span class="f-step"><span class="f-dot"></span>' + label + "</span>";
  const d = trkFormatDate(v.date);
  if (v.state === "pass") return '<span class="f-step"><span class="f-dot pass"></span>' + label + ' <span class="f-date">' + esc(d) + "</span></span>";
  if (v.state === "fail") return '<span class="f-step"><span class="f-dot fail"></span>' + label + ' <span class="f-date">' + esc(d) + " 挂</span></span>";
  if (v.state === "skip") return '<span class="f-step"><span class="f-dot"></span>' + label + " <span>跳过</span></span>";
  if (v.state === "wait") return '<span class="f-step"><span class="f-dot wait"></span>' + label + ' <span class="f-date wait">' + esc(d) + " 等结果</span></span>";
  if (v.state === "todo") return '<span class="f-step"><span class="f-dot todo"></span>' + label + ' <span class="f-date todo">' + esc(d) + " 待</span></span>";
  return "";
}
function resultHtml(job) {
  if (job.result === "offer") return '<span class="res-offer">Offer</span>';
  if (job.result === "fail" || job.result === "giveup") return '<span class="tag" style="background:#f1f3f6;color:#98a2b3;">' + RESULT_LABEL[job.result] + "</span>";
  return "";
}
function starState(job) {
  if (job.result === "fail" || job.result === "giveup") return "off";
  if (hasFutureInterview(job)) return "auto";
  if (job.pinnedAt) return "on";
  return "off";
}
function isPlaceholderTitle(job) {
  const t = String(job.title || "").trim();
  return !t || t === "岗位名称待补充" || t === "待补充";
}

/* 单张卡片模板（横版：星标 → 公司/岗位/标签 → 流程条 → meta → 操作） */
function cardHtml(job) {
  const c = trkCompanyOf(job) || { name: "?" };
  const offerDeadlineTs = job.offerDeadline ? trkLocalMidnight(job.offerDeadline) : 0;
  const offerUrgent = offerDeadlineTs && offerDeadlineTs - Date.now() > 0 && offerDeadlineTs - Date.now() <= 7 * 24 * 3600 * 1000;
  const dead = job.result === "fail" || job.result === "giveup";
  const urgent = !dead && (urgentIn24h(job) || urgentWrittenDeadline(job) || (job.result === "offer" && offerUrgent));
  const star = starState(job);
  const flow = stageList(job).map((x) => flowStepHtml(x.label, x.v)).join("");
  const meta = [];
  if (job.appliedDate) meta.push('<span class="m-item">投递 ' + esc(trkFormatDate(job.appliedDate)) + "</span>");
  if (job.city) meta.push('<span class="m-item">📍 ' + esc(job.city) + "</span>");
  if (job.interviewAt && !dead && job.result !== "offer" && !interviewSettled(job)) {
    const iv = trkLocalIvStr(job.interviewAt);
    meta.push('<span class="m-item ' + (urgentIn24h(job) ? "urgent" : "") + '">🎯 面试 ' + esc(iv) + (urgentIn24h(job) ? " · 24h 内" : "") + "</span>");
  }
  const wdl = writtenDeadlineTs(job);
  if (wdl && !dead) {
    const wd = trkFmtDateTime(wdl);
    const uw = urgentWrittenDeadline(job);
    meta.push('<span class="m-item' + (uw ? " urgent" : "") + '">⏰ 笔试截止 ' + esc(wd) + (uw ? " · 48h 内" : "") + "</span>");
  }
  if (job.result === "offer") {
    if (job.offerDeadline) {
      const od = job.offerDeadline.slice(5);
      const odUrgent = offerDeadlineTs && offerDeadlineTs - Date.now() > 0 && offerDeadlineTs - Date.now() <= 3 * 24 * 3600 * 1000;
      meta.push('<span class="m-item' + (odUrgent ? " urgent" : "") + '">🎗 Offer 截止 ' + esc(od) + (odUrgent ? " · 3 天内" : "") + "</span>");
    } else {
      meta.push('<span class="m-item">🎗 有效期待确认</span>');
    }
  }
  if (job.todo && (job.todo.text || job.todo.due) && !dead) {
    const tdue = job.todo.due ? trkLocalMidnight(job.todo.due) : 0;
    const urgt = tdue && tdue > Date.now() && tdue - Date.now() <= 48 * 3600 * 1000;
    meta.push('<span class="m-item' + (urgt ? " urgent" : "") + '" title="' + esc(job.todo.text || "") + '">⏳ 待办' +
      (job.todo.due ? " 截止 " + esc(job.todo.due.slice(5)) : "") +
      (job.todo.text ? "：" + esc(job.todo.text) : "") + (urgt ? " · 48h 内" : "") + "</span>");
  }
  if (job.note) meta.push('<span class="m-item m-note" data-act="toggle-note" title="点击展开 / 收起完整备注">📝 <span class="note-text">' + esc(job.note) + '</span><span class="note-toggle"></span></span>');
  return (
    '<div class="job-card' + (urgent ? " urgent" : "") + (job.result === "offer" ? " job-offer" : "") + '" id="card-' + job.id + '">' +
    '<button class="star ' + star + '" data-act="pin" data-id="' + job.id + '" title="' +
      (star === "auto" ? "面试自动置顶，修改面试时间可调整排序" : (star === "on" ? "取消置顶" : "置顶此投递")) + '">' +
      (star === "off" ? "☆" : "★") + "</button>" +
    '<div class="card-main">' +
      '<div class="card-top">' +
        '<span class="company">' + esc(c.name) + "</span>" +
        (isPlaceholderTitle(job)
          ? '<button class="job-title-fill" data-act="edit" data-id="' + job.id + '" title="岗位名未填，点击补全">＋ 补全岗位名</button>'
          : '<span class="job-title">' + esc(job.title) + "</span>") +
        '<span class="tag ' + esc(job.workType || "unknown") + '">' + (WORK_TYPE_LABEL[job.workType] || "未知") + "</span>" +
        resultHtml(job) +
      "</div>" +
      '<div class="flow">' + flow + "</div>" +
      '<div class="meta">' + meta.join("") + "</div>" +
    "</div>" +
    '<div class="card-actions">' +
      '<button class="btn btn-primary" data-act="edit" data-id="' + job.id + '">更新</button>' +
    "</div>" +
    "</div>"
  );
}

/* 分组渲染（第一性原理：求职者先看「进行中」，终态沉底） */
function trkRenderList() {
  const jobs = sortJobs(filteredJobs());
  const empty = $("trkEmpty");
  if (jobs.length === 0) {
    $("trkList").innerHTML = "";
    empty.hidden = false;
    empty.textContent = trkState.filter.workType
      ? '暂无「' + (WORK_TYPE_LABEL[trkState.filter.workType] || trkState.filter.workType) + '」的岗位。可在「更新」弹窗中选择工作类型后保存，或用智能识别录入。'
      : "暂无符合条件的投递记录 · 点「＋ 新增投递」或使用智能识别录入";
    return;
  }
  empty.hidden = true;
  const groups = [
    { g: "1", label: "进行中", icon: "⚡" },
    { g: "1.5", label: "Offer 待确认", icon: "🎗", test: offerPending },
    { g: "0", label: "已投待进展", icon: "📥" },
    { g: "2", label: "已挂 / 放弃", icon: "✖" },
  ];
  let html = "";
  for (const gr of groups) {
    const list2 = jobs.filter((j) => (gr.test ? gr.test(j) : String(jobGroup(j)) === gr.g));
    if (list2.length === 0) continue;
    html += '<div class="group-head"><span class="gi">' + gr.icon + "</span>" + gr.label + '<span class="cnt">' + list2.length + "</span></div>" + list2.map(cardHtml).join("");
  }
  $("trkList").innerHTML = html;
}

/* 是否出现在置顶栏（Offer 待确认 / 未来面试 / 手动置顶）——置顶与待办互斥去重 */
function inPinnedBar(job) {
  if (job.result === "fail" || job.result === "giveup") return false;
  if (offerPending(job)) return true;
  const ia = job.interviewAt ? new Date(job.interviewAt).getTime() : null;
  if (ia && !isNaN(ia) && ia > Date.now()) return true;
  return !!job.pinnedAt;
}
function trkRenderPinned() {
  const box = $("trkPinned");
  const offerItems = [];
  const items = [];
  for (const job of trkState.jobs) {
    const cname = (trkCompanyOf(job) || {}).name;
    if (job.result === "fail" || job.result === "giveup") continue;
    if (offerPending(job)) {
      offerItems.push({ id: job.id, name: cname + "｜" + job.title, time: "Offer 截止 " + (job.offerDeadline || "").slice(5) });
      continue;
    }
    const ia = job.interviewAt ? new Date(job.interviewAt).getTime() : null;
    if (ia && !isNaN(ia) && ia > Date.now()) {
      items.push({ t: ia, kind: "面试", name: cname + "｜" + job.title, time: "面试 " + trkLocalIvStr(job.interviewAt), remove: null, id: job.id });
    } else if (job.pinnedAt) {
      items.push({ t: new Date(job.pinnedAt).getTime(), kind: "置顶", name: cname + "｜" + job.title, time: "", remove: "unpin-job", id: job.id });
    }
  }
  items.sort((a, b) => (a.kind === b.kind ? a.t - b.t : (a.kind === "面试" ? -1 : 1)));
  if (offerItems.length === 0 && items.length === 0) {
    box.innerHTML = '<span class="pinned-empty">暂无置顶 · 有面试的投递会自动置顶，也可点击行首星标手动置顶</span>';
    return;
  }
  const chip = (it, offer) =>
    '<span class="pin-chip' + (offer ? " offer" : "") + '" data-id="' + it.id + '" title="点击跳转到该投递">' +
    (offer ? '<span class="k">🎗</span>' : '<span class="k">' + it.kind + "</span>") +
    "<b>" + esc(it.name) + "</b>" +
    (it.time ? '<span class="tag" style="background:#eef4ff;color:#2563eb;">' + esc(it.time) + "</span>" : "") +
    (it.remove ? '<button class="unpin" data-act="' + it.remove + '" data-id="' + it.id + '" title="取消置顶">✕</button>' : "") +
    "</span>";
  let html = "";
  if (offerItems.length) {
    html += '<div class="pin-sec"><span class="pin-sec-title">🎗 Offer 待确认</span>' + offerItems.map((it) => chip(it, true)).join("") + "</div>";
  }
  if (items.length) {
    html += '<div class="pin-sec"><span class="pin-sec-title">📌 置顶</span>' + items.map((it) => chip(it, false)).join("") + "</div>";
  }
  box.innerHTML = html;
}

/* 节点提醒（时间升序 + 同投递同天去重 + 未来 7 天 / Offer 14 天窗口） */
function trkRenderReminders() {
  const bar = $("trkReminder");
  const items = [];
  const now = Date.now();
  const day7 = now + 7 * 24 * 3600 * 1000;
  const day14 = now + 14 * 24 * 3600 * 1000;
  const todayStart = trkLocalMidnight(trkLocalToday());
  for (const job of trkState.jobs) {
    const cname = (trkCompanyOf(job) || {}).name;
    if (job.result === "fail" || job.result === "giveup") continue;
    if (inPinnedBar(job)) continue;
    if (job.interviewAt && !interviewSettled(job)) {
      const t = new Date(job.interviewAt).getTime();
      if (!isNaN(t) && t >= now && t <= day7) {
        items.push({ key: job.id + "|" + trkFmtDateTime(t).slice(0, 10), pri: 3, ts: t, ddl: false, id: job.id, text: trkFmtDateTime(t).slice(5) + " 面试｜" + cname + " " + job.title });
      }
    }
    if (job.offerDeadline) {
      const t = trkLocalMidnight(job.offerDeadline);
      if (t && t >= now && t <= day14) {
        items.push({ key: job.id + "|" + job.offerDeadline, pri: 4, ts: t, ddl: true, id: job.id, text: job.offerDeadline.slice(5) + " Offer 截止｜" + cname + " " + job.title });
      }
    }
    const wdl = writtenDeadlineTs(job);
    if (wdl && wdl >= now && wdl <= day7) {
      items.push({ key: job.id + "|" + trkFmtDateTime(wdl).slice(0, 10), pri: 2, ts: wdl, ddl: true, id: job.id, text: trkFmtDateTime(wdl).slice(5) + " 笔试截止｜" + cname + " " + job.title });
    }
    if (job.todo && job.todo.due) {
      const t = trkLocalMidnight(job.todo.due);
      if (t && t >= now && t <= day7) {
        items.push({ key: job.id + "|" + job.todo.due, pri: 2, ts: t, ddl: true, id: job.id, text: job.todo.due.slice(5) + " 待办截止｜" + cname + " " + job.title + (job.todo.text ? "：" + job.todo.text : "") });
      }
    }
    for (const x of stageList(job)) {
      if (x.v && x.v.state === "todo" && x.v.date) {
        const t = trkLocalMidnight(x.v.date);
        if (t && t >= todayStart && t <= day7) {
          items.push({ key: job.id + "|" + x.v.date, pri: 1, ts: t, ddl: false, id: job.id, text: x.v.date.slice(5) + " " + x.label + "｜" + cname + " " + job.title });
        }
      }
    }
  }
  const byKey = new Map();
  for (const it of items) {
    const cur = byKey.get(it.key);
    if (!cur || it.pri > cur.pri) byKey.set(it.key, it);
  }
  const top = [...byKey.values()].sort((a, b) => a.ts - b.ts).slice(0, 10);
  let html = "";
  if (top.length === 0) {
    html += '<span class="rem-item none">未来 7 天暂无节点</span>';
  } else {
    html += top.map((it) => {
      const urgent = it.ddl || (it.ts - now > 0 && it.ts - now <= 24 * 3600 * 1000);
      return '<span class="rem-item' + (urgent ? " urgent" : "") + '" data-id="' + it.id + '" title="点击跳转到该投递">' + esc(it.text) + "</span>";
    }).join("");
  }
  bar.innerHTML = html;
}

function trkRenderCityOptions() {
  const sel = $("trkCity");
  const cities = [...new Set(trkState.jobs.flatMap((j) => trkJobCities(j)))].sort();
  const cur = sel.value;
  sel.innerHTML = '<option value="">城市：全部</option>' + cities.map((c) => '<option value="' + esc(c) + '">' + esc(c) + "</option>").join("");
  sel.value = trkState.filter.city || cur;
}

/* 跳转定位（提醒/置顶点击）：被筛选隐藏则重置过滤 + 高亮闪烁 */
function trkJumpToJob(jobId) {
  if (!trkState.jobs.some((j) => j.id === jobId)) return;
  if (!filteredJobs().some((j) => j.id === jobId)) {
    trkState.filter = { tab: "all", kw: "", status: "", city: "", workType: "" };
    $("trkSearch").value = "";
    $("trkStatus").value = "";
    $("trkCity").value = "";
    document.querySelectorAll("#trkTabs .ttab").forEach((b) => b.classList.toggle("active", b.dataset.tab === "all"));
    trkRender();
  }
  const el = document.getElementById("card-" + jobId);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 2400);
}

/* 实时时钟（跟随系统时间，24H 制） */
function trkStartClock() {
  if (window.__trkClockOn) return;
  window.__trkClockOn = true;
  const el = $("trkClock");
  if (!el) return;
  const upd = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    el.textContent = d.getFullYear() + "/" + p(d.getMonth() + 1) + "/" + p(d.getDate()) + "  " + p(d.getHours()) + ":" + p(d.getMinutes());
  };
  upd();
  setInterval(upd, 1000);
}

/* 离线/在线模式：未配置 API Key → 智能识别栏置灰 */
function trkRenderQuickParse() {
  const sec = document.querySelector(".quick-parse");
  const ta = $("trkQpText");
  const btn = $("btnTrkQp");
  const hint = $("trkQpHint");
  const off = !trkState.aiOnline;
  if (sec) sec.classList.toggle("off", off);
  if (ta) ta.disabled = off;
  if (btn) btn.disabled = off;
  if (hint) hint.textContent = off
    ? "未配置 API Key，智能识别不可用 · 点「⚙ 控制台」配置并测试连接后启用"
    : "识别结果先进入确认表单，核对无误后再保存";
}
async function trkCheckAiOnline() {
  try {
    const res = await fetch("/api/ai/test", { method: "POST" });
    const d = await res.json();
    trkState.aiOnline = !!(d && d.ok);
  } catch (_) { trkState.aiOnline = false; }
  trkRenderQuickParse();
}

function trkGuessWorkType(title) {
  if (/秋招|校招|应届/i.test(title)) return "autumn";
  return "unknown";
}

/* ---------- 统一渲染 + 备注展开 ---------- */
function trkInitNoteToggles() {
  document.querySelectorAll("#trkList .m-note").forEach((el) => {
    if (el.closest(".job-card") && el.closest(".job-card").classList.contains("note-open")) return;
    const text = el.querySelector(".note-text");
    if (!text) return;
    const truncated = text.scrollWidth > text.clientWidth + 1;
    el.classList.toggle("expandable", truncated);
  });
}
function trkRender() {
  trkRenderPinned();
  trkRenderList();
  trkRenderReminders();
  trkRenderCityOptions();
  trkRenderQuickParse();
  trkInitNoteToggles();
}

/* ---------- 弹窗 / toast ---------- */
function trkShowModal(show) {
  $("trkModalMask").classList.toggle("hidden", !show);
  if (!show) return;
  const save = $("btnTrkSave");
  if (trkState.modalMode === "form") {
    save.classList.remove("hidden");
    save.onclick = trkSaveForm;
  } else {
    save.classList.add("hidden");
    save.onclick = null;
  }
}
function trkToast(msg, isError) {
  const t = $("trkToast");
  t.textContent = msg;
  t.style.background = isError ? "#dc2626" : "#1f2733";
  t.classList.add("show");
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove("show"), 2600);
}

/* ---------- 表单控件联动 ---------- */
function trkCompanySelChange() {
  const sel = $("f-company-sel");
  const inp = $("f-company");
  if (!sel || !inp) return;
  const isNew = sel.value === "__new__";
  inp.style.display = isNew ? "block" : "none";
  if (isNew) inp.focus();
}
function trkCitySelChange() {
  const sel = $("f-city-sel");
  const inp = $("f-city");
  if (!sel || !inp) return;
  const isOther = sel.value === "__other__";
  inp.style.display = isOther ? "block" : "none";
  if (isOther) inp.focus();
}
function trkSyncOfferDeadline() {
  const w = $("f-offer-deadline-wrap");
  if (!w) return;
  const r = $("f-result");
  w.style.display = (r && r.value === "offer") ? "" : "none";
}
function trkSetStageRow(key, v) {
  const row = document.querySelector('#trkModalBody .stage-row[data-key="' + key + '"]');
  if (!row) return;
  row.querySelector('[data-f="state"]').value = (v && v.state) || "";
  row.querySelector('[data-f="date"]').value = ((v && v.date) || "").slice(0, 10);
  const dl = row.querySelector('[data-f="deadline"]');
  if (dl && v && v.deadline) dl.value = String(v.deadline).slice(0, 16);
}

/* ---------- 智能识别：识别结果 → 确认表单 ---------- */
function trkRenderAiConfirm(data) {
  trkState.aiDraft = data || {};
  trkOpenAddModal({ forceCat: true });
  const d = trkState.aiDraft;
  const comp = (d.company || "").trim();
  const compSel = $("f-company-sel");
  if (comp && [...compSel.options].some((o) => o.value === comp)) compSel.value = comp;
  else if (comp) { compSel.value = "__new__"; $("f-company").value = comp; $("f-company").style.display = "block"; }
  $("f-title").value = d.title || "";
  if (d.workType && WORK_TYPE_LABEL[d.workType]) {
    const wtEl = $("f-work-type");
    if (wtEl) wtEl.value = d.workType;
  }
  if (d.city) {
    const citySel = $("f-city-sel");
    if ([...citySel.options].some((o) => o.value === d.city)) citySel.value = d.city;
    else { citySel.value = "__other__"; $("f-city").value = d.city; $("f-city").style.display = "block"; }
  }
  $("f-url").value = d.url || "";
  $("f-applied").value = (d.appliedDate || "").slice(0, 10);
  if (d.interviewAt) $("f-interview").value = String(d.interviewAt).replace(" ", "T").slice(0, 16);
  $("f-note").value = d.note || "";
  if (d.todo) {
    $("f-todo-text").value = d.todo.text || "";
    $("f-todo-due").value = String(d.todo.due || "").slice(0, 10);
  }
  if (d.offerDeadline) $("f-offer-deadline").value = String(d.offerDeadline).slice(0, 10);
  const s = d.stages || {};
  if (d.interviewAt) {
    s.resume = s.resume || { date: "", state: null, deadline: null };
    s.written = s.written || { date: "", state: null, deadline: null };
    if (!s.interviews) s.interviews = [];
    if (s.interviews.length === 0) s.interviews.push({ date: String(d.interviewAt).slice(0, 10), state: "todo" });
  }
  if (s.resume || s.written || (s.interviews || []).length || s.hr) normalizeStages(s, { interviewAt: d.interviewAt || null });
  if (s.resume) trkSetStageRow("resume", s.resume);
  if (s.written) trkSetStageRow("written", s.written);
  (s.interviews || []).forEach((v, i) => {
    if (!v || !(v.state || v.date)) return;
    addRoundRow();
    trkSetStageRow("iv" + i, v);
  });
  if (s.hr) trkSetStageRow("hr", s.hr);
  const unc = (d.uncertain || []).filter(Boolean);
  if (unc.length) {
    const box = document.createElement("div");
    box.className = "offer-hint";
    box.innerHTML = "⚠️ 以下信息请核对后保存：" + unc.map(esc).join("；");
    $("trkModalBody").insertBefore(box, $("trkModalBody").firstChild);
  }
  $("trkModalTitle").textContent = "确认识别结果，可修改";
  trkState.modalMode = "form";
  trkShowModal(true);
}

/* 识别核心：/api/ai/parse → 确认表单 */
async function trkDoAiParse(text) {
  try {
    const res = await fetch("/api/ai/parse", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 400 && /API Key/.test(data.error || "")) {
        trkToast("未配置 API Key，请先在控制台配置并测试连接", true);
        return;
      }
      throw new Error(data.error || "识别失败");
    }
    trkRenderAiConfirm(data.data);
  } catch (e) { trkToast(e.message, true); }
}
async function trkQuickParse() {
  const text = $("trkQpText").value.trim();
  if (!text) { trkToast("请先粘贴需要识别的信息", true); $("trkQpText").focus(); return; }
  $("btnTrkQp").disabled = true;
  $("btnTrkQp").textContent = "识别中…";
  try {
    await trkDoAiParse(text);
    $("trkQpText").value = "";
  } finally {
    $("btnTrkQp").disabled = false;
    $("btnTrkQp").textContent = "识别补充";
  }
}

/* ---------- 表单：新增（公司/城市下拉优先，识别确认模式工作类型必选） ---------- */
function trkOpenAddModal(opts) {
  opts = opts || {};
  trkState.editingJobId = null;
  trkState.modalMode = "form";
  trkState.aiForceCat = !!opts.forceCat;
  $("trkModalTitle").textContent = "新增投递";
  const wtOpts = opts.forceCat
    ? '<option value="">请选择工作类型…</option><option value="autumn">秋招</option><option value="convert">有转正实习</option><option value="nonconvert">日常实习</option><option value="unknown">未知</option>'
    : '<option value="unknown">未知</option><option value="autumn">秋招</option><option value="convert">有转正实习</option><option value="nonconvert">日常实习</option>';
  const companyOpts = trkState.companies.map((c) => '<option value="' + esc(c.name) + '">' + esc(c.name) + "</option>").join("");
  const cityOpts = [...new Set(trkState.jobs.flatMap((j) => trkJobCities(j)))].sort().map((c) => '<option value="' + esc(c) + '">' + esc(c) + "</option>").join("");
  $("trkModalBody").innerHTML =
    '<div class="form-grid">' +
    '<div class="form-item"><label>公司名 <span class="req">*</span></label>' +
      '<select id="f-company-sel" onchange="trkCompanySelChange()"><option value="">请选择公司…</option>' + companyOpts + '<option value="__new__">＋ 新建公司…</option></select>' +
      '<input id="f-company" placeholder="输入新公司名" style="display:none;margin-top:6px;"></div>' +
    '<div class="form-item"><label>岗位名 <span class="req">*</span></label><input id="f-title" placeholder="如：大模型推理优化实习生"></div>' +
    '<div class="form-item"><label>工作类型 <span class="req" style="display:' + (opts.forceCat ? "inline" : "none") + '">*</span><span class="req-tip" style="display:' + (opts.forceCat ? "inline" : "none") + '">识别信息不含工作类型，请确认</span></label><select id="f-work-type">' + wtOpts + "</select></div>" +
    '<div class="form-item"><label>城市</label>' +
      '<select id="f-city-sel" onchange="trkCitySelChange()"><option value="">不限</option>' + cityOpts + '<option value="__other__">自定义…</option></select>' +
      '<input id="f-city" placeholder="输入城市，多个用 / 分隔，如 北京/上海" style="display:none;margin-top:6px;"></div>' +
    '<div class="form-item"><label>链接</label><input id="f-url" placeholder="https://…"></div>' +
    '<div class="form-item"><label>投递日期</label><input id="f-applied" type="date" value="' + trkLocalToday() + '"></div>' +
    '<div class="form-item"><label>面试时间，用于提醒与置顶</label><input id="f-interview" type="datetime-local"></div>' +
    '<div class="form-item full"><label>备注 / 下一动作</label><textarea id="f-note" rows="2" placeholder="如：48h 内完成测评；08-15 二面…"></textarea></div>' +
    '<div class="form-item"><label>待办事项</label><input id="f-todo-text" placeholder="如：8-15 前完成注册并预约面试"></div>' +
    '<div class="form-item"><label>待办截止日期</label><input id="f-todo-due" type="date"></div>' +
    '<div id="f-offer-deadline-wrap" style="display:none;"><div class="form-item"><label>Offer 截止日期</label><input id="f-offer-deadline" type="date" title="Offer 有效期，如 8-24 前确认"></div></div>' +
    "</div>" +
    '<div class="hint" style="margin:10px 0 4px;">流程环节：</div>' +
    stageRowHtml("resume", STAGE_LABELS.resume, { date: "", state: null }, false) +
    stageRowHtml("written", STAGE_LABELS.written, { date: "", state: null }, false) +
    '<div id="roundWrap"><button type="button" class="btn add-round" data-act="add-round">＋ 添加一轮面试</button></div>' +
    stageRowHtml("hr", STAGE_LABELS.hr, { date: "", state: null }, false) +
    '<div class="hint">带 <span class="req">*</span> 为必填项：公司名、岗位名、工作类型；其余均为选填。</div>';
  trkShowModal(true);
}

/* ---------- 一行环节控件（笔试行附带 DDL）；读取 / 追加面试轮 ---------- */
function stageRowHtml(key, label, v, removable) {
  const st = (v && v.state) || "";
  const d = trkFormatDate((v && v.date) || "");
  const dl = (v && v.deadline) ? v.deadline.slice(0, 16) : "";
  const dlInput = key === "written"
    ? '<input type="datetime-local" data-f="deadline" value="' + esc(dl) + '" title="笔试截止时间，如 48h 内做测评">'
    : "";
  return (
    '<div class="stage-row" data-kind="' + (String(key).startsWith("iv") ? "iv" : "fx") + '" data-key="' + key + '">' +
    '<span class="sn">' + label + "</span>" +
    '<select data-f="state">' +
      '<option value="">留空，未到</option>' +
      '<option value="pass"' + (st === "pass" ? " selected" : "") + ">通过</option>" +
      '<option value="wait"' + (st === "wait" ? " selected" : "") + ">等结果</option>" +
      '<option value="todo"' + (st === "todo" ? " selected" : "") + ">待进行，有预约/截止时间</option>" +
      '<option value="fail"' + (st === "fail" ? " selected" : "") + ">被挂</option>" +
      '<option value="skip"' + (st === "skip" ? " selected" : "") + ">跳过，无此环节</option>" +
    "</select>" +
    '<input type="date" data-f="date" value="' + esc(d) + '">' +
    dlInput +
    (removable ? '<button type="button" class="rm" data-rm="1" title="删除该轮面试">✕</button>' : "") +
    "</div>"
  );
}
function readStageRow(row) {
  const st = row.querySelector('[data-f="state"]').value;
  const date = row.querySelector('[data-f="date"]').value;
  const dlEl = row.querySelector('[data-f="deadline"]');
  const dl = dlEl ? dlEl.value : "";
  if (!st && !date && !dl) return { date: "", state: null };
  const out = { date: date || "", state: st || null };
  if (dl) out.deadline = dl + ":00";
  return out;
}
function hasStageContent(v) { return !!(v && (v.state || v.date)); }
function addRoundRow() {
  const wrap = $("roundWrap");
  if (!wrap) return;
  const btn = wrap.querySelector('[data-act="add-round"]');
  const n = wrap.querySelectorAll('.stage-row[data-kind="iv"]').length;
  const tmp = document.createElement("div");
  tmp.innerHTML = stageRowHtml("iv" + n, (CN_NUM[n] || String(n + 1)) + "面", { date: "", state: null }, true);
  btn.insertAdjacentElement("beforebegin", tmp.firstElementChild);
}

/* 状态机合法性转移：fail 清空后续 / pass 下一环节 todo / 隐含前置通过（有面试→简历+笔试自动通过） */
function normalizeStages(stages, job) {
  const seq = [];
  for (const k of ["resume", "written"]) if (stages[k]) seq.push(stages[k]);
  seq.push(...(stages.interviews || []));
  if (stages.hr) seq.push(stages.hr);
  if (job && (job.result === "fail" || job.result === "giveup")) {
    let lastAct = -1;
    for (let i = 0; i < seq.length; i++) {
      const v = seq[i];
      if (v && (v.state === "pass" || v.state === "wait" || v.state === "todo" || v.state === "fail" || v.date)) lastAct = i;
    }
    if (lastAct >= 0 && seq[lastAct].state !== "fail") seq[lastAct].state = "fail";
  }
  let failIdx = -1;
  for (let i = 0; i < seq.length; i++) {
    if (seq[i] && seq[i].state === "fail") { failIdx = i; break; }
  }
  if (failIdx >= 0) {
    seq.forEach((v, i) => { if (i > failIdx) { v.date = ""; v.state = null; v.deadline = null; } });
  }
  for (let i = 0; i < seq.length - 1; i++) {
    if (seq[i] && seq[i].state === "pass" && seq[i + 1] && !seq[i + 1].state) {
      seq[i + 1].state = "todo";
      seq[i + 1].date = seq[i + 1].date || "";
    }
  }
  const resume = stages.resume, written = stages.written;
  const ivs = stages.interviews || [];
  const hasInterviewInfo = !!(job && job.interviewAt) || ivs.some((v) => v && v.state && v.state !== "skip");
  if (written && written.state === "pass" && resume && !resume.state) resume.state = "pass";
  if (hasInterviewInfo) {
    if (written && !written.state) written.state = "pass";
    if (resume && !resume.state) resume.state = "pass";
  }
  return stages;
}

/* ---------- 更新弹窗（v3 动态环节） ---------- */
function trkOpenEditModal(jobId) {
  const job = trkState.jobs.find((j) => j.id === jobId);
  if (!job) return;
  trkState.editingJobId = jobId;
  trkState.modalMode = "form";
  const c = trkCompanyOf(job);
  $("trkModalTitle").textContent = "更新进度｜" + (c ? c.name : "") + " " + job.title;
  const s = job.stages || {};
  let rows = "";
  for (const k of ["resume", "written"]) {
    rows += stageRowHtml(k, STAGE_LABELS[k], s[k] || { date: "", state: null }, false);
  }
  let ivRows = "";
  (s.interviews || []).forEach((v, i) => {
    ivRows += stageRowHtml("iv" + i, (CN_NUM[i] || String(i + 1)) + "面", v, true);
  });
  const hrRow = stageRowHtml("hr", STAGE_LABELS.hr, s.hr || { date: "", state: null }, false);
  const offerHint = (allStagesPassed(job) && !job.result)
    ? '<div class="offer-hint">🎉 流程环节全部通过——若已拿到 Offer，点击「🏆 标记为 Offer」或在下方选择最终结果。</div>'
    : "";
  $("trkModalBody").innerHTML =
    '<div class="form-grid">' +
    '<div class="form-item"><label>公司名称 <span class="req">*</span></label><input id="f-company" value="' + esc(c ? c.name : "") + '" placeholder="修改后将同步该公司全部岗位"></div>' +
    '<div class="form-item"><label>岗位名称 <span class="req">*</span></label><input id="f-title" value="' + esc(job.title || "") + '" placeholder="如：大模型推理优化实习生"></div>' +
    '<div class="form-item"><label>工作类型</label><select id="f-work-type">' +
      '<option value="autumn"' + (job.workType === "autumn" ? " selected" : "") + ">秋招</option>" +
      '<option value="convert"' + (job.workType === "convert" ? " selected" : "") + ">有转正实习</option>" +
      '<option value="nonconvert"' + (job.workType === "nonconvert" ? " selected" : "") + ">日常实习</option>" +
      '<option value="unknown"' + (job.workType === "unknown" || !job.workType ? " selected" : "") + ">未知</option>" +
    "</select></div>" +
    '<div class="form-item"><label>面试时间，用于提醒与置顶</label><input id="f-interview" type="datetime-local" value="' + esc(job.interviewAt ? trkLocalIvStr(job.interviewAt).replace(" ", "T") : "") + '"></div>' +
    '<div class="form-item"><label>最终结果</label><div class="result-row"><select id="f-result" onchange="trkSyncOfferDeadline()">' +
      '<option value="">无，流程中</option>' +
      '<option value="offer"' + (job.result === "offer" ? " selected" : "") + ">Offer</option>" +
      '<option value="fail"' + (job.result === "fail" ? " selected" : "") + ">挂</option>" +
      '<option value="giveup"' + (job.result === "giveup" ? " selected" : "") + ">放弃</option>" +
    "</select>" +
    '<button type="button" class="btn btn-offer" data-act="mark-offer" title="全部环节标记为通过并设为 Offer">🏆 标记为 Offer</button></div></div>' +
    '<div id="f-offer-deadline-wrap" style="display:' + (job.result === "offer" ? "" : "none") + ';"><div class="form-item"><label>Offer 截止日期</label><input id="f-offer-deadline" type="date" value="' + esc(job.offerDeadline || "") + '" title="如 8-24 前确认"></div></div>' +
    '<div class="form-item"><label>待办事项</label><input id="f-todo-text" value="' + esc((job.todo || {}).text || "") + '" placeholder="如：8-15 前完成注册并预约面试"></div>' +
    '<div class="form-item"><label>待办截止日期</label><input id="f-todo-due" type="date" value="' + esc((job.todo || {}).due || "") + '"></div>' +
    "</div>" +
    offerHint +
    '<div class="hint" style="margin:10px 0 4px;">流程环节：留空即未到；通过后下一环节自动待进行；被挂后自动终止</div>' +
    rows +
    '<div id="roundWrap">' + ivRows + '<button type="button" class="btn add-round" data-act="add-round">＋ 添加一轮面试</button></div>' +
    hrRow +
    '<div class="form-item full" style="margin-top:10px;"><label>备注 / 下一动作</label><textarea id="f-note" rows="2">' + esc(job.note || "") + "</textarea></div>";
  trkShowModal(true);
  if (isPlaceholderTitle(job)) {
    setTimeout(() => { const t = $("f-title"); if (t) t.focus(); }, 60);
  }
}

/* ---------- 保存（新增 / 更新 / 识别确认；自动保存 + 重排） ---------- */
async function trkSaveForm() {
  try {
    let offerPending = false;
    if (trkState.editingJobId === null) {
      document.querySelectorAll("#trkModalBody .err").forEach((el) => el.classList.remove("err"));
      const sel = $("f-company-sel");
      const company = (sel && sel.value && sel.value !== "__new__") ? sel.value : $("f-company").value.trim();
      const title = $("f-title").value.trim();
      const wtEl = $("f-work-type");
      const workType = wtEl ? wtEl.value : "unknown";
      let miss = [];
      if (!company) { miss.push("公司名"); if (sel) sel.classList.add("err"); $("f-company").classList.add("err"); }
      if (!title) { miss.push("岗位名"); $("f-title").classList.add("err"); }
      if (trkState.aiForceCat && !workType) { miss.push("工作类型"); if (wtEl) wtEl.closest(".form-item").classList.add("err"); }
      if (miss.length) { trkToast("请完成必填项：" + miss.join("、"), true); return; }
      const dup = trkState.jobs.find((j) => j.title === title && (trkCompanyOf(j) || {}).name === company);
      if (dup) { trkToast("该公司下已存在同名岗位，建议改为「更新」", true); return; }
      let c = trkState.companies.find((cc) => cc.name === company);
      if (!c) {
        c = { id: trkNewId(), name: company, pinnedAt: null, note: "" };
        trkState.companies.push(c);
      }
      const citySel = $("f-city-sel");
      const city = (citySel && citySel.value && citySel.value !== "__other__") ? citySel.value : $("f-city").value.trim();
      const stages = {};
      document.querySelectorAll('#trkModalBody .stage-row[data-kind="fx"]').forEach((row) => { stages[row.dataset.key] = readStageRow(row); });
      const iv = [];
      document.querySelectorAll('#trkModalBody .stage-row[data-kind="iv"]').forEach((row) => { iv.push(readStageRow(row)); });
      while (iv.length > 0 && !hasStageContent(iv[iv.length - 1])) iv.pop();
      stages.interviews = iv;
      const job = {
        id: trkNewId(), companyId: c.id, title, workType, city,
        url: $("f-url").value.trim(),
        appliedDate: $("f-applied").value || trkLocalToday(),
        interviewAt: $("f-interview").value || null,
        note: $("f-note").value.trim(),
        todo: (() => { const t = $("f-todo-text").value.trim(); const d = $("f-todo-due").value; return (t || d) ? { text: t, due: d || "" } : null; })(),
        offerDeadline: $("f-offer-deadline").value || null,
        stages, result: null, updatedAt: trkNowIso(), pinnedAt: null,
      };
      normalizeStages(stages, job);
      if (stageList(job).some((x) => x.v.state === "fail")) job.result = "fail";
      trkState.jobs.push(job);
    } else {
      const job = trkState.jobs.find((j) => j.id === trkState.editingJobId);
      if (!job) return;
      document.querySelectorAll("#trkModalBody .err").forEach((el) => el.classList.remove("err"));
      const cName = $("f-company").value.trim();
      const tName = $("f-title").value.trim();
      let miss = [];
      if (!cName) { miss.push("公司名称"); $("f-company").classList.add("err"); }
      if (!tName) { miss.push("岗位名称"); $("f-title").classList.add("err"); }
      if (miss.length) { trkToast("请完成必填项：" + miss.join("、"), true); return; }
      const cEdit = trkCompanyOf(job);
      if (cEdit && cEdit.name !== cName) cEdit.name = cName;
      if (job.title !== tName) job.title = tName;
      job.interviewAt = $("f-interview").value || null;
      job.result = $("f-result").value || null;
      if (job.result === "fail" || job.result === "giveup") job.interviewAt = null;
      job.note = $("f-note").value.trim();
      const wtEl = $("f-work-type");
      if (wtEl) job.workType = wtEl.value || "unknown";
      const tt = $("f-todo-text").value.trim();
      const dd = $("f-todo-due").value;
      job.todo = (tt || dd) ? { text: tt, due: dd || "" } : null;
      job.offerDeadline = job.result === "offer" ? ($("f-offer-deadline").value || null) : null;
      const stages = {};
      document.querySelectorAll('#trkModalBody .stage-row[data-kind="fx"]').forEach((row) => { stages[row.dataset.key] = readStageRow(row); });
      const iv = [];
      document.querySelectorAll('#trkModalBody .stage-row[data-kind="iv"]').forEach((row) => { iv.push(readStageRow(row)); });
      while (iv.length > 0 && !hasStageContent(iv[iv.length - 1])) iv.pop();
      stages.interviews = iv;
      normalizeStages(stages, job);
      job.stages = stages;
      if (stageList(job).some((x) => x.v.state === "fail") && !job.result) job.result = "fail";
      job.updatedAt = trkNowIso();
      offerPending = allStagesPassed(job) && !job.result;
    }
    trkSaveData();
    trkShowModal(false);
    trkState.aiDraft = null;
    trkRender();
    trkToast(offerPending ? "已保存：流程环节全部通过，可更新最终结果为 Offer" : "已保存并按优先级重排");
  } catch (e) {
    trkToast("保存失败：" + e.message, true);
  }
}

/* ---------- 置顶（行首星标，仅单投递） ---------- */
function trkTogglePinJob(jobId) {
  const job = trkState.jobs.find((j) => j.id === jobId);
  if (!job) return;
  if (hasFutureInterview(job)) { trkToast("该投递由面试自动置顶，修改面试时间即可调整排序"); return; }
  job.pinnedAt = job.pinnedAt ? null : trkNowIso();
  job.updatedAt = trkNowIso();
  trkSaveData();
  trkRender();
  const el = document.getElementById("card-" + job.id);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 2400);
  }
  trkToast(job.pinnedAt ? "已置顶，置顶栏按置顶先后排列" : "已取消置顶");
}

/* ---------- 事件绑定 ---------- */
function trkBindEvents() {
  $("btnTrkAdd").addEventListener("click", () => trkOpenAddModal());
  $("btnTrkQp").addEventListener("click", trkQuickParse);
  $("btnTrkClose").addEventListener("click", () => trkShowModal(false));
  $("btnTrkCancel").addEventListener("click", () => trkShowModal(false));
  $("trkModalMask").addEventListener("click", (e) => { if (e.target === $("trkModalMask")) trkShowModal(false); });
  $("trkSearch").addEventListener("input", (e) => { trkState.filter.kw = e.target.value.trim(); trkRender(); });
  $("trkStatus").addEventListener("change", (e) => { trkState.filter.status = e.target.value; trkRender(); });
  $("trkCity").addEventListener("change", (e) => { trkState.filter.city = e.target.value; trkRender(); });
  $("trkWorkType").addEventListener("change", (e) => { trkState.filter.workType = e.target.value; trkRender(); });
  $("trkTabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".ttab");
    if (!btn) return;
    document.querySelectorAll("#trkTabs .ttab").forEach((b) => b.classList.toggle("active", b === btn));
    trkState.filter.tab = btn.dataset.tab;
    trkRender();
  });
  $("trkList").addEventListener("click", (e) => {
    const pin = e.target.closest('[data-act="pin"]');
    const edit = e.target.closest('[data-act="edit"]');
    const note = e.target.closest('[data-act="toggle-note"]');
    if (pin) trkTogglePinJob(pin.dataset.id);
    else if (edit) trkOpenEditModal(edit.dataset.id);
    else if (note) {
      const nEl = note.closest(".m-note");
      if (nEl && nEl.classList.contains("expandable")) {
        const card = note.closest(".job-card");
        if (card) card.classList.toggle("note-open");
      }
    }
  });
  $("trkPinned").addEventListener("click", (e) => {
    const unpin = e.target.closest('[data-act="unpin-job"]');
    if (unpin) { trkTogglePinJob(unpin.dataset.id); return; }
    const chip = e.target.closest(".pin-chip[data-id]");
    if (chip) trkJumpToJob(chip.dataset.id);
  });
  $("trkReminder").addEventListener("click", (e) => {
    const it = e.target.closest(".rem-item[data-id]");
    if (it) trkJumpToJob(it.dataset.id);
  });
  window.addEventListener("resize", () => {
    clearTimeout(window.__trkNoteTimer);
    window.__trkNoteTimer = setTimeout(trkInitNoteToggles, 150);
  });
  $("trkModalBody").addEventListener("click", (e) => {
    const add = e.target.closest('[data-act="add-round"]');
    if (add) { addRoundRow(); return; }
    const rm = e.target.closest("[data-rm]");
    if (rm) { rm.closest(".stage-row").remove(); return; }
    const mo = e.target.closest('[data-act="mark-offer"]');
    if (mo) {
      document.querySelectorAll('#trkModalBody .stage-row select[data-f="state"]').forEach((sel) => {
        if (sel.value !== "skip") sel.value = "pass";
      });
      $("f-result").value = "offer";
      trkSyncOfferDeadline();
      return;
    }
  });
}

/* 进入追踪板块：加载数据 + 全量渲染 + 时钟 + 在线探测 */
function trkInitRender() {
  trkLoadData();
  trkRender();
  trkStartClock();
  trkCheckAiOnline();
}
/* ================= 深浅主题 ================= */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  const b = $("btnTheme");
  if (b) b.textContent = t === "dark" ? "☀️" : "🌙";
}
(function initTheme() {
  const saved = localStorage.getItem("jobhunter_theme");
  const t = saved || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(t);
  const b = $("btnTheme");
  if (b) b.addEventListener("click", () => {
    const nt = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("jobhunter_theme", nt);
    applyTheme(nt);
  });
})();
trkBindEvents();
(async function init() {
  switchBoard("resume");
  renderLanding();  // 默认先展示着陆页，点击板块卡片后进入对应板块
})();

/* ================= 通用工具 ================= */
/* 标题兜底：name/company 为空时取 desc 前 14 字，避免"未命名项目/实习"假数据 */
function headOf(name, desc) {
  const n = (name || "").trim();
  if (n) return n;
  const d = (desc || "").trim().replace(/\s+/g, " ");
  return d ? (d.length > 14 ? d.slice(0, 14) + "…" : d) : "";
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

/* ================= 全流程 HITL interrupt 生命周期（N2 画像追问 / N9 投递确认） ================= */
async function postJson(url, body) {
  const resp = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

let _runThreadId = null;

async function apiRun(payload) {
  /* 发起全流程；遇 interrupt 弹面板等用户答复，循环 resume 直到 done，返回聚合数据。 */
  let r = await postJson("/api/run", payload);
  _runThreadId = r.thread_id;
  while (r.status === "interrupt") {
    const it = (r.interrupts || [])[0] || {};
    let decision;
    if (it.type === "ask_profile") decision = await askProfile(it);
    else if (it.type === "confirm_resume") decision = await confirmResume(it);
    else throw new Error("未知人工确认点：" + (it.type || "unknown"));
    if (decision === null || decision === undefined) throw new Error("流程已取消");
    r = await postJson("/api/run/resume", { thread_id: _runThreadId, resume: decision });
  }
  if (r.status !== "done") throw new Error("流程异常终止：" + JSON.stringify(r));
  return r.data;
}

function askProfile(it) {
  /* N2 画像缺失追问：按 missing_fields 渲染表单，返回 answers（skills[]/experience[]） */
  return new Promise((resolve) => {
    $("runModalTitle").textContent = "补充画像信息（第 " + (it.ask_round + 1) + " 轮）";
    const missing = it.missing_fields || [];
    const rows = [];
    if (missing.includes("skills")) {
      rows.push(`<div class="field"><label class="field-label">技能（逗号分隔）</label>
        <input id="ipSkills" class="input" placeholder="如：Python, PyTorch, C++"></div>`);
    }
    if (missing.includes("experience")) {
      rows.push(`<div class="field"><label class="field-label">项目/实习经历（每行一条：角色｜公司｜描述）</label>
        <textarea id="ipExp" class="input" rows="4" placeholder="如：算法实习生｜某公司｜轨迹预测算法开发"></textarea></div>`);
    }
    $("runModalBody").innerHTML = `<div class="d-section"><p class="d-tip">以下画像字段缺失，补充后继续：</p>${rows.join("")}</div>`;
    $("runModalFoot").innerHTML = `<button class="btn" id="runModalOk">继续</button>
      <button class="btn btn-ghost" id="runModalCancel">取消</button>`;
    $("runModalMask").classList.remove("hidden");
    const finish = () => {
      const answers = {};
      if (missing.includes("skills")) {
        const s = ($("ipSkills")?.value || "").split(/[,，]/).map((x) => x.trim()).filter(Boolean);
        if (s.length) answers.skills = s;
      }
      if (missing.includes("experience")) {
        const exp = ($("ipExp")?.value || "").split("\n").map((x) => x.trim()).filter(Boolean)
          .map((line) => { const [role, company, ...rest] = line.split(/[｜|]/).map((x) => x.trim()); return { role: role || "项目经历", company: company || "", desc: rest.join("｜") || line }; });
        if (exp.length) answers.experience = exp;
      }
      $("runModalMask").classList.add("hidden");
      resolve(answers);
    };
    const cancel = () => { $("runModalMask").classList.add("hidden"); resolve({}); };
    $("runModalOk").addEventListener("click", finish);
    $("runModalCancel").addEventListener("click", cancel);
    $("btnCloseRunModal").addEventListener("click", cancel);
    $("runModalMask").addEventListener("click", (e) => { if (e.target === $("runModalMask")) cancel(); });
  });
}

function confirmResume(it) {
  /* N9 投递确认：展示 简历摘要 + 达标岗位 + 投递清单（只推荐不引导），返回 {action, feedback|reason} */
  return new Promise((resolve) => {
    $("runModalTitle").textContent = "确认简历与投递清单";
    const resume = it.resume || {};
    const matched = it.matched || [];
    const plan = it.submission_plan || {};
    // summary 兼容两种形态：mock 返回字符串，real 可能返回 [{text}] 数组（与 renderSheet 一致）
    const summary = Array.isArray(resume.summary)
      ? resume.summary.map((s) => s.text || "").join(" ").trim()
      : String(resume.summary || "").trim();
    const planHtml = (plan.tiers || []).map((t) =>
      `<h5>${esc(t.name || "")}</h5>` +
      (t.jobs || []).map((j) => `<div class="row-line">${esc(j.title)} · ${esc(j.company)} · ${j.score}分</div>`).join("")).join("")
      || "<div class='muted'>（清单为空）</div>";
    $("runModalBody").innerHTML = `
      <div class="d-section">
        <h4>简历摘要</h4>
        <pre class="md-view">${esc(summary || resume.text || "(无摘要)")}</pre>
        <h4>达标岗位（${matched.length}）</h4>
        <div>${matched.map((m) => `<div class="row-line">${esc(m.title)} · ${esc(m.company)} · ${m.score}分</div>`).join("") || (plan.total ? "<div class='muted'>暂无 ≥70 分强匹配岗位，以下投递清单为次优候选</div>" : "<div class='muted'>无</div>")}</div>
        <h4>投递清单（${plan.total ?? 0}，确认后可在「投递清单」板块查看与导出）</h4>
        ${planHtml}
        <div class="field"><label class="field-label">修改意见 / 拒绝理由（选填）</label>
          <textarea id="ipDecision" class="input" rows="3"></textarea></div>
      </div>`;
    $("runModalFoot").innerHTML = `<button class="btn" id="rmApprove">✓ 确认使用</button>
      <button class="btn btn-ghost" id="rmModify">✎ 提修改</button>
      <button class="btn btn-danger" id="rmReject">✕ 拒绝</button>`;
    $("runModalMask").classList.remove("hidden");
    const bind = (id, action) => $(id).addEventListener("click", () => {
      const note = ($("ipDecision")?.value || "").trim();
      $("runModalMask").classList.add("hidden");
      if (action === "approve") resolve({ action: "approve" });
      else if (action === "modify") resolve({ action: "modify", feedback: note });
      else resolve({ action: "reject", reason: note });
    });
    bind("rmApprove", "approve");
    bind("rmModify", "modify");
    bind("rmReject", "reject");
    $("btnCloseRunModal").addEventListener("click", () => { $("runModalMask").classList.add("hidden"); resolve(null); });
    $("runModalMask").addEventListener("click", (e) => { if (e.target === $("runModalMask")) { $("runModalMask").classList.add("hidden"); resolve(null); } });
  });
}
function kvHtml(rows) {
  return rows.map(([k, v]) => `<div class="kv-item"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`).join("") || "<div class='empty-hint'>无数据</div>";
}
