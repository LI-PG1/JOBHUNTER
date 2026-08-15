/* JS-Agent 前端逻辑：左栏流程 + 控制台悬浮框 */
"use strict";

const $ = (id) => document.getElementById(id);

const CITIES = ["北京","上海","广州","深圳","杭州","成都","武汉","南京","苏州","西安","重庆","天津","长沙","郑州","青岛","宁波","厦门","合肥","福州","济南","大连","沈阳","昆明","哈尔滨","石家庄","南昌","贵阳","南宁","太原","长春","乌鲁木齐","兰州","海口","呼和浩特","银川","西宁"];

/* ---------- 工具 ---------- */
async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `请求失败 (${res.status})`);
  }
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const LINE_LABEL = { application: "应用", inference: "推理", both: "双线", other: "其他" };

/* ---------- 左栏流程指示 ---------- */
function setStep(n) {
  document.querySelectorAll("#stepsNav .pstep").forEach((el) => {
    el.classList.toggle("active", Number(el.dataset.step) === n);
  });
}

/* ---------- 城市/初始化 ---------- */
function initCity() {
  const sel = $("city");
  sel.innerHTML = `<option value="">请选择</option>` + CITIES.map((c) => `<option>${c}</option>`).join("");
}

/* ---------- 配置卡片（厂商/模型两级选择器） ---------- */
let _providers = [];

async function refreshConsole() {
  const st = await api("/api/console/status");
  _providers = st.providers || [];
  renderProviderSelector();
  renderPlugins((st.plugins && st.plugins.components) || {}, st.plugins || {});
  renderConstraint(st.constraint_mode);
  // 顶部通道 pill
  const chain = (st.plugins && st.plugins.search_chain) || "探测中";
  $("chainPill").textContent = "搜索通道：" + chain;
}

function currentProvider() {
  const pid = $("providerSelect").value;
  return _providers.find((p) => p.id === pid) || null;
}

function renderProviderSelector() {
  const sel = $("providerSelect");
  const prev = sel.value;
  sel.innerHTML = _providers
    .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}${p.has_key ? " ✓ 已配置" : ""}</option>`)
    .join("");
  if (prev && _providers.some((p) => p.id === prev)) sel.value = prev;
  renderModels();
}

function renderModels() {
  const p = currentProvider();
  const msel = $("modelSelect");
  msel.innerHTML = (p ? p.models : [])
    .map((m) => `<option ${m === p.model ? "selected" : ""}>${esc(m)}</option>`)
    .join("");
  // Key 输入框状态
  const keyEl = $("apiKeyInput");
  keyEl.value = "";
  keyEl.placeholder = p && p.has_key ? "已保存 Key，留空则使用已存值" : "sk-...";
  $("btnDeleteKey").classList.toggle("hidden", !(p && p.has_key));
  const msg = $("keyMsg");
  msg.textContent = "";
  msg.style.color = "";
  // 顶部就绪状态
  const hasKey = _providers.some((x) => x.has_key);
  const ready = $("keyReady");
  ready.textContent = hasKey ? "✓ 已配置可用 Key" : "未配置 Key";
  ready.style.color = hasKey ? "#177b3a" : "#c0392b";
  // 未配置 Key 时「开始匹配」置灰
  renderKeyList();
  syncStartBtn();
}

/* 控制台「已配置 Key」状态条：列出已保存 Key 的厂商，提供独立删除入口 */
function renderKeyList() {
  const bar = $("keyListBar");
  const list = _providers.filter((x) => x.has_key);
  if (list.length === 0) {
    bar.innerHTML = `<span class="key-item dim">未配置 Key（开始匹配已置灰）</span>`;
    return;
  }
  bar.innerHTML =
    `<span class="key-label">已配置 Key：</span>` +
    list
      .map(
        (p) =>
          `<span class="key-item"><b>${esc(p.name)}</b>${p.model ? `（${esc(p.model)}）` : ""}` +
          `<button class="btn btn-sm btn-danger" data-delkey="${esc(p.id)}">删除</button></span>`
      )
      .join("");
}

function syncStartBtn() {
  $("btnStart").disabled = !_providers.some((x) => x.has_key);
}

async function saveKey() {
  const p = currentProvider();
  const model = $("modelSelect").value;
  const key = $("apiKeyInput").value.trim();
  const msg = $("keyMsg");
  if (!p) { msg.textContent = "请选择厂商"; return; }
  if (!key) { msg.textContent = "请填写 API Key"; return; }
  msg.textContent = "保存中...";
  try {
    await api("/api/console/keys", { method: "POST", body: JSON.stringify({ provider_id: p.id, model, api_key: key }) });
    msg.textContent = "✓ 已保存";
    msg.style.color = "#177b3a";
    await refreshConsole();
  } catch (e) { msg.textContent = `✗ ${e.message}`; msg.style.color = "#c0392b"; }
}

async function testKey() {
  const p = currentProvider();
  const model = $("modelSelect").value;
  const key = $("apiKeyInput").value.trim();
  const msg = $("keyMsg");
  if (!p) { msg.textContent = "请选择厂商"; return; }
  msg.textContent = "测试中...";
  try {
    const body = { model };
    if (key) body.api_key = key;
    const r = await api(`/api/console/keys/${p.id}/test`, { method: "POST", body: JSON.stringify(body) });
    msg.textContent = r.ok ? `✓ 连通 ${r.elapsed_s}s` : `✗ ${r.error}`;
    msg.style.color = r.ok ? "#177b3a" : "#c0392b";
  } catch (e) { msg.textContent = `✗ ${e.message}`; msg.style.color = "#c0392b"; }
}

async function deleteKey(pid) {
  const p = pid ? _providers.find((x) => x.id === pid) : currentProvider();
  const msg = $("keyMsg");
  if (!p) return;
  try {
    await api(`/api/console/keys/${p.id}`, { method: "DELETE" });
    msg.textContent = `已删除 ${p.name} Key`;
    msg.style.color = "#177b3a";
    await refreshConsole();
  } catch (e) { msg.textContent = `✗ ${e.message}`; msg.style.color = "#c0392b"; }
}

function renderPlugins(components, plug) {
  const busy = plug.busy;
  const list = $("plugList");
  list.innerHTML = "";
  Object.entries(components).forEach(([cid, c]) => {
    const item = document.createElement("div");
    item.className = "plug-item";
    const st = c.installed ? `<span class="ok">已安装</span>` : `<span class="miss">未安装</span>`;
    const gray = c.gray ? `<span class="gray">(灰区)</span>` : "";
    item.innerHTML = `
      <div class="plug-info"><span>${esc(c.name)} ${gray} <span class="gray">${esc(c.size)}</span></span>${st}</div>
      <div class="plug-ops">
        <button class="btn btn-sm" data-pcid="${esc(cid)}" data-pact="configure" ${busy ? "disabled" : ""}>配置</button>
        <button class="btn btn-sm btn-danger" data-pcid="${esc(cid)}" data-pact="uninstall" ${busy ? "disabled" : ""}>卸载</button>
      </div>`;
    list.appendChild(item);
  });
  $("plugChain").textContent = plug.search_chain || "探测中";
  // 实时状态（busy 时单插件按钮已在渲染中置灰）
  const status = $("plugStatus");
  if (busy) {
    status.textContent = busy === "configuring" ? "配置中..." : "卸载中...";
    status.className = "plug-status busy";
  } else {
    status.textContent = "空闲";
    status.className = "plug-status";
  }
}

function renderConstraint(mode) {
  document.querySelectorAll("#constraintRow .btn").forEach((b) => {
    b.classList.toggle("btn-primary", b.dataset.mode === mode);
    b.classList.toggle("btn-sm", true);
  });
}

async function pollPlugins() {
  // 轮询插件状态直到 busy 为空
  const t = setInterval(async () => {
    try {
      const st = await api("/api/console/plugins");
      renderPlugins(st.components || {}, st);
      if (!st.busy) { clearInterval(t); }
    } catch { clearInterval(t); }
  }, 1200);
}

/* ---------- 匹配 ---------- */
let currentJob = null;

async function startMatch() {
  const profileText = $("profileText").value.trim();
  const city = $("city").value;
  const maxResults = $("maxResults").value;
  const types = Array.from(document.querySelectorAll("#companyTypes input:checked")).map((i) => i.value);

  if (!city) { alert("请选择意向城市"); return; }
  if (!profileText || profileText.length < 20) { alert("请填写个人画像（至少 20 字）"); return; }

  $("btnStart").disabled = true;
  $("btnCancel").classList.remove("hidden");
  $("progressWrap").classList.remove("hidden");
  setStep(3);
  setProgress(2, "提交任务...");

  try {
    const body = { profile_text: profileText, city, max_results: Number(maxResults), company_types: types };
    const { job_id } = await api("/api/match", { method: "POST", body: JSON.stringify(body) });
    currentJob = job_id;
    pollMatch(job_id);
  } catch (e) {
    setProgress(0, "");
    syncStartBtn();
    $("btnCancel").classList.add("hidden");
    setStep(1);
    showError(e.message);
  }
}

function setProgress(pct, msg) {
  $("progressBar").style.width = pct + "%";
  $("progressMsg").textContent = msg || "";
}

async function pollMatch(jobId) {
  const t = setInterval(async () => {
    try {
      const st = await api(`/api/match/${jobId}`);
      if (st.progress !== undefined) { setProgress(st.progress, st.message || ""); }
      if (st.status === "done") {
        clearInterval(t);
        syncStartBtn();
        $("btnCancel").classList.add("hidden");
        renderResult(st.result);
      } else if (st.status === "failed") {
        clearInterval(t);
        syncStartBtn();
        $("btnCancel").classList.add("hidden");
        setProgress(0, "");
        showError(st.error || "任务失败");
      } else if (st.status === "cancelling") {
        setProgress(st.progress, "正在取消...");
      }
    } catch (e) {
      clearInterval(t);
      syncStartBtn();
      showError(e.message);
    }
  }, 1000);
}

function renderResult(result) {
  $("resultError").classList.add("hidden");
  $("btnRetry").classList.add("hidden");
  $("resultEmpty").classList.add("hidden");
  $("resultSummary").classList.remove("hidden");
  $("resultSummary").textContent = result.summary || "";
  const jobs = result.jobs || [];
  const meta = [];
  meta.push(`共收录 ${jobs.length} 个岗位`);
  if (result.rounds_used) meta.push(`搜索轮次 ${result.rounds_used}`);
  if (result.backends && result.backends.length) meta.push(`通道 ${result.backends.join(" / ")}`);
  const dbg = result._debug || {};
  if (!jobs.length && dbg.searched > 0 && dbg.washed === 0) {
    meta.push(`洗涤筛除 ${dbg.searched} 条（搜索通道返回非招聘页，建议稍后重试或配置 Tavily/智谱 Key）`);
  }
  if (result._qa_note) meta.push(result._qa_note);
  $("resultMeta").textContent = meta.join(" ｜ ");

  const body = $("resultBody");
  body.innerHTML = "";
  jobs.forEach((j, i) => {
    const score = j.match_score ?? 0;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="idx">${i + 1}</td>
      <td class="job">${esc(j.title)}</td>
      <td>${esc(j.company)}</td>
      <td>${esc(j.city)}</td>
      <td>${esc(j.salary) || "-"}</td>
      <td class="score">${score}%</td>
      <td><span class="line line-${esc(j.skill_line || "other")}">${LINE_LABEL[j.skill_line] || "-"}</span></td>
      <td>${esc(j.industry || "-")}</td>
      <td>${esc(j.degree || "-")}</td>
      <td>${esc(j.experience || "-")}</td>
      <td>${score >= 80 ? '<span class="st st-ok">已收录</span>' : '<span class="st st-gap">需补足</span>'}</td>
      <td>${j.source_url ? `<a href="${esc(j.source_url)}" target="_blank">查看</a>` : "-"}</td>`;
    body.appendChild(tr);
  });
  if (!jobs.length) {
    body.innerHTML = "";
    $("gapList").innerHTML = "";
    $("resultFiles").innerHTML = "";
    const empty = $("resultEmpty");
    empty.classList.remove("hidden");
    empty.innerHTML =
      "<b>未收录到符合条件的岗位</b><br>可能原因：<br>" +
      "1. 岗位匹配度低于收录阈值（80%）被排除<br>" +
      "2. 本轮搜索未发现新岗位，或信息已超时效（60 天）<br>" +
      "3. 画像技能覆盖不足<br><br>" +
      "建议下一步：控制台放宽约束强度（loose）→ 补充画像技能 → 重新执行匹配。";
    return;
  }

  // 补足清单
  const gapEl = $("gapList");
  const gaps = jobs.filter((j) => (j.match_score ?? 100) < 80);
  gapEl.innerHTML = "";
  if (gaps.length) {
    gapEl.innerHTML = "<h4>需补足岗位（60-80%）</h4>";
    gaps.forEach((j) => {
      const missing = (j.missing_skills || []).join("、") || "无";
      gapEl.innerHTML += `<div class="gap-item">• ${esc(j.company)} · ${esc(j.title)}（${j.match_score}%）缺：${esc(missing)}${j.gap_tips ? ` ｜ ${esc(j.gap_tips)}` : ""}</div>`;
    });
  }

  // 文件
  const files = result.files || {};
  const fEl = $("resultFiles");
  fEl.innerHTML = "";
  if (files.md || files.html) {
    fEl.innerHTML = `<b>结果已保存：</b>` + [files.md, files.html].filter(Boolean).map((f) => `<code>${esc(f)}</code>`).join("<br>");
  }
}

function showError(msg) {
  $("resultError").textContent = msg;
  $("resultError").classList.remove("hidden");
  // 纠错态：提供重试入口（UXD：错误可预期、可恢复、有引导）
  $("btnRetry").classList.remove("hidden");
}

/* ---------- 事件绑定 ---------- */
document.addEventListener("DOMContentLoaded", () => {
  initCity();

  // 左栏流程：第一步引导打开控制台
  $("stepsNav").addEventListener("click", (e) => {
    const step = e.target.closest(".pstep");
    if (step && Number(step.dataset.step) === 1) {
      $("consoleMask").classList.remove("hidden");
      refreshConsole().catch((err) => showError(err.message));
    }
  });

  // 控制台悬浮框：顶部常驻栏按钮打开，遮罩/关闭按钮关闭
  $("btnConsole").addEventListener("click", () => {
    $("consoleMask").classList.remove("hidden");
    refreshConsole().catch((e) => showError(e.message));
  });
  $("btnCloseConsole").addEventListener("click", () => $("consoleMask").classList.add("hidden"));
  $("consoleMask").addEventListener("click", (e) => {
    if (e.target === $("consoleMask")) $("consoleMask").classList.add("hidden");
  });

  // 厂商/模型两级联动
  $("providerSelect").addEventListener("change", renderModels);
  $("btnSaveKey").addEventListener("click", saveKey);
  $("btnTestKey").addEventListener("click", testKey);
  $("btnDeleteKey").addEventListener("click", () => deleteKey());

  // 「已配置 Key」状态条：独立删除入口（事件委托）
  $("keyListBar").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-delkey]");
    if (btn) deleteKey(btn.dataset.delkey);
  });

  // 插件：单插件独立配置/卸载（事件委托）
  $("plugList").addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-pcid]");
    if (!btn) return;
    const cid = btn.dataset.pcid;
    const act = btn.dataset.pact;
    try {
      await api(`/api/console/plugins/${cid}/${act}`, { method: "POST" });
      pollPlugins();
    } catch (err) { $("plugStatus").textContent = err.message; }
  });

  // 约束强度
  document.querySelectorAll("#constraintRow .btn").forEach((b) => {
    b.addEventListener("click", async () => {
      try {
        await api("/api/console/constraint", { method: "POST", body: JSON.stringify({ mode: b.dataset.mode }) });
        renderConstraint(b.dataset.mode);
      } catch (e) { alert(e.message); }
    });
  });

  // 匹配
  $("btnStart").addEventListener("click", startMatch);
  $("btnRetry").addEventListener("click", () => {
    $("resultError").classList.add("hidden");
    $("btnRetry").classList.add("hidden");
    startMatch();
  });
  $("btnCancel").addEventListener("click", async () => {
    if (currentJob) {
      try { await api(`/api/match/${currentJob}`, { method: "DELETE" }); } catch { /* ignore */ }
    }
  });

  // 初始加载控制台状态（顶部通道 pill）
  refreshConsole().catch(() => {});
});
