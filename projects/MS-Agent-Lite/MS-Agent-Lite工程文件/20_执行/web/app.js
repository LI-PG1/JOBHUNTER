// app.js — 面试准备助手（纯文本版）面板前端逻辑（原生 JS，零构建）
(function () {
  "use strict";

  // ---------- 运行环境检查 ----------
  // 直接双击 index.html（file:// 协议）打开时没有本地 Node 服务，所有 /api/* 请求都会失败，
  // 上传/生成等核心功能无法使用——此时给出明确启动指引，而不是让页面静默失效。
  if (location.protocol === "file:") {
    document.body.innerHTML =
      '<div style="max-width:620px;margin:80px auto;padding:30px 34px;background:#fff;border:1px solid #e5e7eb;border-radius:14px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,\'Microsoft YaHei\',sans-serif;line-height:1.9;color:#1f2937;box-shadow:0 8px 30px rgba(17,24,39,.08)">' +
      '<h2 style="margin:0 0 12px;font-size:20px;color:#111827">⚠ 请通过本地服务打开本面板</h2>' +
      '<p style="margin:0 0 10px">当前是直接双击打开（file:// 协议），<b>缺少本地 Node 服务</b>，简历上传、生成等功能均无法使用。</p>' +
      '<p style="margin:0 0 14px"><b>正确启动方式（任选其一）：</b></p>' +
      '<ol style="margin:0 0 16px;padding-left:22px">' +
      '<li><b>双击启动器</b>：进入发布包第一层，双击 <code>启动面试准备助手.bat</code>——自动检查 Node、启动服务并打开浏览器（免终端）。</li>' +
      '<li><b>命令行启动</b>：打开终端，进入 <code>MS-Agent-Lite工程文件\\20_执行</code> 目录，执行 <code>npm install</code>（首次）后 <code>npm start</code>。</li>' +
      '</ol>' +
      '<p style="margin:0;font-size:13px;color:#6b7280">服务启动后请访问 <code>http://localhost:8900/</code>，在该页面内进行上传与生成。</p>' +
      '</div>';
    return; // 终止面板初始化，避免无意义报错
  }

  // ---------- DOM ----------
  const $ = id => document.getElementById(id);
  const els = {
    inpCompany: $("inpCompany"),
    selZone: $("selZone"), zoneHint: $("zoneHint"),
    dropResume: $("dropResume"), inpResume: $("inpResume"), fileMeta: $("fileMeta"), fileInfo: $("fileInfo"),
    btnRemoveFile: $("btnRemoveFile"), fileParseState: $("fileParseState"), resumePreview: $("resumePreview"), resumeNeedTip: $("resumeNeedTip"),
    inpJdUrl: $("inpJdUrl"), btnFetchJd: $("btnFetchJd"), inpJd: $("inpJd"),
    urlRows: $("urlRows"), btnAddUrlRow: $("btnAddUrlRow"), inpRefInfo: $("inpRefInfo"), refInfoCount: $("refInfoCount"),
    btnStart: $("btnStart"), inputError: $("inputError"),
    cardProcess: $("cardProcess"), taskBadge: $("taskBadge"), fileList: $("fileList"),
    progFill: $("progFill"), progPct: $("progPct"),
    logBox: $("logBox"), btnCancel: $("btnCancel"),
    cardResult: $("cardResult"), verifyBadge: $("verifyBadge"), retryArea: $("retryArea"),
    checkBox: $("checkBox"),
    qualityBox: $("qualityBox"),
    previewEmpty: $("previewEmpty"), previewFrame: $("previewFrame"),
    mask: $("mask"), drawer: $("drawer"), btnSettings: $("btnSettings"), btnCloseDrawer: $("btnCloseDrawer"),
    provList: $("provList"), pName: $("pName"), pUrl: $("pUrl"), pModel: $("pModel"), pKey: $("pKey"),
    pCap: $("pCap"), btnSaveProvider: $("btnSaveProvider"), btnTestProvider: $("btnTestProvider"), provMsg: $("provMsg"),
    cliToolsList: $("cliToolsList"), btnProbeCli: $("btnProbeCli"), cliToolsMsg: $("cliToolsMsg"),
    ocrJsStatus: $("ocrJsStatus"),
    webSearchStatus: $("webSearchStatus"), webSearchKey: $("webSearchKey"),
    btnSaveWebSearch: $("btnSaveWebSearch"), webSearchMsg: $("webSearchMsg"),
    toast: $("toast"), provStatus: $("provStatus"),
    cardApiKey: $("cardApiKey"), keyStatus: $("keyStatus"), selPreset: $("selPreset"), presetHint: $("presetHint"),
    selModel: $("selModel"),
    kpName: $("kpName"), kpUrl: $("kpUrl"), kpModel: $("kpModel"), kpKey: $("kpKey"),
    btnKeySave: $("btnKeySave"), keyMsg: $("keyMsg")
  };

  // ---------- 状态 ----------
  const FILE_NAMES = ["面试主线", "01_自我介绍", "02_项目深挖", "03_技术场景题", "04_反问环节", "05_面经分析与面试题库", "附录_数字口径", "00_公司背景"];
  const state = { taskId: null, es: null, resume: null, urls: [], fileStatus: {}, log: [], providerTestName: null,
    // M3：质量回路状态（每文件最新裁决 / done 汇总 / 强制回炉 busy 标记）
    qualityByFile: {}, qualitySummary: null, qualityBusy: {} };

  // 8 步固定权重进度条（R3：pending→parsing→fetching→generating→building→verifying→reviewing→rework→checking→done）
  // generating 区间（20→88）内按 8 个文件完成数细分推进
  const STEP_WEIGHTS = { pending: 3, parsing: 10, fetching: 20, generating: 20, building: 90, verifying: 96, reviewing: 97, rework: 97.5, checking: 98, done: 100 };
  function setProgress(pct, label) {
    if (!els.progFill || !els.progPct) return;
    const v = Math.max(0, Math.min(100, Math.round(pct)));
    els.progFill.style.width = v + "%";
    els.progPct.textContent = (label || "") + (label ? " " : "") + v + "%";
  }

  // 左栏「当前该做什么」动态引导行：用户不读文档，常驻提示随流程推进自动切换（v0.4.15）
  function setRailNote(html) {
    const el = document.getElementById("railNote");
    if (el) el.innerHTML = html;
  }

  // 常用厂商预置：选择厂商后自动列出该厂商常见模型（models），选中即自动填入配置名称 / 模型名 / 接口地址；
  // keySample 用于 API Key 输入框的示例提示（随所选厂商 + 模型动态变化）。
  // 注：Base URL / 模型名以各平台最新官方文档为准，预置仅为常用默认值；展开「确认身份信息」仍可手动修改
  const PRESETS = {
    deepseek: {
      name: "deepseek", label: "DeepSeek",
      baseUrl: "https://api.deepseek.com/v1/chat/completions",
      keySample: "sk-...",
      // 命名规范：id 为通用显示名（界面展示），apiId 为官方 API 模型名（请求发送），二者分离
      // DeepSeek 真实模型名：deepseek-v4-flash / deepseek-v4-pro；deepseek-chat / deepseek-reasoner 为历史兼容别名（勿用作 apiId）
      models: [
        { id: "DeepSeek-V4-Flash", apiId: "deepseek-v4-flash", note: "低成本、新用户送额度，日常够用" },
        { id: "DeepSeek-V4-Pro", apiId: "deepseek-v4-pro", note: "更强推理，成本更高" }
      ]
    },
    zhipu: {
      name: "zhipu", label: "智谱 AI",
      baseUrl: "https://open.bigmodel.cn/api/paas/v4/chat/completions",
      keySample: "长串字母数字",
      models: [
        { id: "glm-4-flash", note: "长期免费，文本生成够用" },
        { id: "glm-4-flash-250414", note: "免费新版本（250414）" },
        { id: "glm-4-plus", note: "更强，价格较高" },
        { id: "glm-4v-flash", note: "视觉模型（免费），可看图" }
      ]
    },
    siliconflow: {
      name: "siliconflow", label: "硅基流动",
      baseUrl: "https://api.siliconflow.cn/v1/chat/completions",
      keySample: "sk-...",
      models: [
        { id: "Qwen/Qwen2.5-7B-Instruct", note: "开源模型聚合，免费档" },
        { id: "Qwen/Qwen2.5-72B-Instruct", note: "大杯开源模型" },
        { id: "deepseek-ai/DeepSeek-V3", note: "DeepSeek 开源版" },
        { id: "THUDM/GLM-4.1V-9B-Thinking", note: "视觉模型，可看图" }
      ]
    },
    openai: {
      name: "openai", label: "OpenAI",
      baseUrl: "https://api.openai.com/v1/chat/completions",
      keySample: "sk-...",
      models: [
        { id: "gpt-4o-mini", note: "性价比高，日常够用" },
        { id: "gpt-4o", note: "综合能力强" },
        { id: "gpt-4.1-mini", note: "新一代性价比档" },
        { id: "gpt-4.1", note: "新一代旗舰档" }
      ]
    },
    qwen: {
      name: "qwen", label: "阿里云百炼（通义千问）",
      baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
      keySample: "sk-...",
      models: [
        { id: "qwen-plus", note: "综合平衡，推荐" },
        { id: "qwen-turbo", note: "更便宜" },
        { id: "qwen-max", note: "最强" },
        { id: "qwen-vl-plus", note: "视觉模型，可看图" }
      ]
    },
    baidu: {
      name: "baidu", label: "百度千帆（文心一言）",
      baseUrl: "https://qianfan.baidubce.com/v2/chat/completions",
      keySample: "长串字母数字",
      models: [
        { id: "ernie-4.0-turbo-8k-latest", note: "低成本档" },
        { id: "ernie-4.0-turbo-128k", note: "长上下文档" },
        { id: "ernie-4.0-8k-latest", note: "更强" },
        { id: "ernie-3.5-8k", note: "经典档" }
      ]
    },
    tencent: {
      name: "tencent", label: "腾讯混元",
      baseUrl: "https://api.hunyuan.cloud.tencent.com/v1/chat/completions",
      keySample: "长串字母数字",
      models: [
        { id: "hunyuan-lite", note: "免费档" },
        { id: "hunyuan-standard", note: "标准档" },
        { id: "hunyuan-pro", note: "旗舰档" },
        { id: "hunyuan-turbo", note: "快速档" }
      ]
    },
    kimi: {
      name: "kimi", label: "Moonshot Kimi",
      baseUrl: "https://api.moonshot.cn/v1/chat/completions",
      keySample: "sk-...",
      models: [
        { id: "kimi-k2.6", note: "现役通用模型，256K 上下文" },
        { id: "kimi-k3", note: "旗舰模型，1M 上下文" }
      ]
    },
    minimax: {
      name: "minimax", label: "MiniMax",
      baseUrl: "https://api.minimax.chat/v1/chat/completions",
      keySample: "eyJ...(JWT)",
      models: [
        { id: "abab6.5s-chat", note: "轻量档" },
        { id: "abab6.5g-chat", note: "标准档" },
        { id: "MiniMax-Text-01", note: "新一代文本模型" }
      ]
    },
    xfyun: {
      name: "xfyun", label: "讯飞星火",
      baseUrl: "https://spark-api-open.xf-yun.com/v1/chat/completions",
      keySample: "APIKey/APISecret（控制台）",
      models: [
        { id: "generalv3.5", note: "常用档" },
        { id: "generalv3", note: "经典档" },
        { id: "4.0Ultra", note: "旗舰档" },
        { id: "lite", note: "轻量免费档" }
      ]
    },
    groq: {
      name: "groq", label: "Groq",
      baseUrl: "https://api.groq.com/openai/v1/chat/completions",
      keySample: "gsk_...",
      models: [
        { id: "llama-3.3-70b-versatile", note: "推理极快" },
        { id: "llama-3.1-8b-instant", note: "轻量快档" },
        { id: "qwen/qwen-2.5-32b", note: "Qwen 开源版" },
        { id: "gemma2-9b-it", note: "Gemma 开源版" }
      ]
    },
    openrouter: {
      name: "openrouter", label: "OpenRouter（模型聚合）",
      baseUrl: "https://openrouter.ai/api/v1/chat/completions",
      keySample: "sk-or-...",
      models: [
        { id: "deepseek/deepseek-chat-v3-0324", note: "DeepSeek 聚合" },
        { id: "meta-llama/llama-3.3-70b-instruct", note: "Llama 聚合" },
        { id: "qwen/qwen-2.5-72b-instruct", note: "Qwen 聚合" },
        { id: "google/gemini-2.0-flash-exp", note: "Gemini 聚合" }
      ]
    }
  };
  // 能力分类选择 → cap 能力标签（系统文本生成需 text，图片理解 / OCR 需 vision；纯文本最省额度）
  // 纯文本版：默认只需 text 能力，vision 仅作图片识别兜底（可选）
  const CAP_MAP = {
    text:        ["text"],
    textvision:  ["text", "vision"],
    multimodal:  ["text", "vision"],
    textocr:     ["text", "vision"]
  };

  // 把后端/API 原始错误翻译成用户能看懂的中文提示（用于自检失败、生成失败等场景）
  function humanTestError(err) {
    const s = String(err || "");
    if (/401|Unauthorized|Authentication|invalid.*key|api.*key/i.test(s)) return "API Key 无效或已过期——请回平台控制台重新复制 Key（注意复制完整、前后无空格）";
    if (/403/.test(s)) return "无权限访问（403）——请检查平台账号权限 / 是否已实名";
    if (/404/.test(s)) return "接口或模型不存在（404）——请核对 Base URL 与模型名";
    if (/429/.test(s)) return "请求过频或额度用尽（429）——稍后重试，或检查平台余额";
    if (/400/.test(s)) return "请求参数不被接受（400）——请核对 Base URL 末尾是否为 /chat/completions";
    if (/timeout|超时|timed out/i.test(s)) return "请求超时——请检查网络后重试";
    if (/没有可用的|文本生成可用条件/.test(s)) return "该配置缺少文本生成能力（cap 需含 text），无法用于生成面试材料";
    return s;
  }

  // ---------- 通用 ----------
  async function api(path, opts) {
    const r = await fetch(path, opts);
    let data = null;
    try { data = await r.json(); } catch (e) { /* 非 JSON */ }
    if (!r.ok) throw new Error((data && data.error) || ("HTTP " + r.status));
    return data;
  }
  let toastTimer = null;
  function toast(msg, ms) {
    els.toast.textContent = msg;
    els.toast.style.display = "block";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { els.toast.style.display = "none"; }, ms || 2600);
  }
  function setBadge(el, status, text) {
    el.className = "badge " + status;
    el.textContent = text;
  }

  // ---------- API Key 一键区（主页面第 1 步） ----------
  function setKeyMsg(cls, text) {
    els.keyMsg.textContent = text;
    els.keyMsg.className = "mini" + (cls ? " " + cls : "");
  }
  // 厂商预置：选厂商 → 自动列出常见模型（② 选择模型）→ 选中自动填入配置名称 / 模型名 / 接口地址；默认 DeepSeek，页面加载即生效
  function updatePresetHint() {
    const p = PRESETS[els.selPreset.value];
    els.presetHint.textContent = p
      ? "已按「" + (p.label || p.name) + "」自动填好配置名称 / 接口地址；在「② 选择模型」选中一个模型后，粘贴 API Key 即可保存自检。"
      : "";
  }
  // 选中的模型同步到「⑤ 模型名」输入框，并把 API Key 输入框提示换为该厂商 + 该模型的示例（v0.4.16）
  // 命名规范：输入框填入官方 API 名（apiId），下拉与提示展示通用显示名（id）
  function applyModel() {
    const p = PRESETS[els.selPreset.value];
    const sel = els.selModel.value;
    const m = (p.models || []).find(x => x.id === sel);
    const apiModel = (m && m.apiId) || sel;
    if (sel) els.kpModel.value = apiModel;
    els.kpModel.placeholder = sel ? "" : "如 glm-4-flash（从平台「模型列表 / 接入文档」复制）";
    els.kpKey.placeholder = p
      ? "粘贴 " + (p.label || p.name) + " API Key（" + (p.keySample || "控制台创建") + "）· 模型 " + (sel || "待选")
      : "sk-... 或 xxxx.yyyy（完整密钥）";
  }
  function applyPreset() {
    const p = PRESETS[els.selPreset.value];
    if (!p) return;
    els.kpName.value = p.name;
    els.kpUrl.value = p.baseUrl;
    const sel = els.selModel;
    const prev = els.kpModel.value;
    sel.innerHTML = "";
    (p.models || []).forEach(m => {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.note ? m.id + "（" + m.note + "）" : m.id;
      sel.appendChild(o);
    });
    const hit = (p.models || []).find(m => m.id === prev || m.apiId === prev);
    if (hit) sel.value = hit.id;
    applyModel();
    updatePresetHint();
  }
  els.selPreset.addEventListener("change", () => {
    applyPreset();
    setKeyMsg("", "");
  });
  els.selModel.addEventListener("change", () => {
    applyModel();
    setKeyMsg("", "");
  });
  applyPreset(); // 页面加载即默认选中 DeepSeek 并自动填入
  // 保存并自检：先写入 config.json，再做一次真实最小请求验证
  els.btnKeySave.addEventListener("click", async () => {
    const body = {
      name: els.kpName.value.trim(),
      baseUrl: els.kpUrl.value.trim(),
      model: els.kpModel.value.trim(),
      apiKey: els.kpKey.value.trim(),
      cap: ["text"]
    };
    // 字段级校验：逐个指出缺什么、去哪填（不用笼统的"必填"）
    const missing = [];
    if (!body.name) missing.push("④ 配置名称");
    if (!body.model) missing.push("⑤ 模型名");
    if (!body.baseUrl) missing.push("⑥ Base URL");
    if (missing.length) {
      setKeyMsg("err", "缺少必填项：" + missing.join("、") + "——可先在上方「🔑 第 1 步」①选择厂商 + ②选择模型自动填入，再核对修改");
      return;
    }
    if (!/^https?:\/\//i.test(body.baseUrl)) { setKeyMsg("err", "⑥ Base URL 格式不对：需以 http:// 或 https:// 开头（如 https://api.xxx.com/v1/chat/completions）"); return; }
    if (!body.apiKey) { setKeyMsg("err", "请粘贴 API Key（③ 输入框）——它是调用大模型的凭证，不可为空"); return; }
    els.btnKeySave.disabled = true;
    setKeyMsg("", "保存并自检中…（真实请求，约需几秒）");
    try {
      // 保存后立即把最新 provider 快照写回 state，供 renderKeyStatus() 渲染（此前丢弃返回值导致状态条一直显示"尚未配置"）
      const pv = await api("/api/providers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      state.providers = pv.providers;
      els.kpKey.value = "";
      const t = await api("/api/providers/" + encodeURIComponent(body.name) + "/test", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: '{"real":true}'
      });
      if (t.ok) {
        markVerified(body.name); // 真实请求通过 → 记录验证状态，状态条才显示绿色
        // 视觉/多模态：自检仅验证文本连通性，明确告知用户（当前流程不调用视觉，不影响生成）
        const capNote = (body.cap || []).includes("vision")
          ? "（视觉能力当前流程不需要，未单独验证；模型不支持看图也不影响生成）"
          : "";
        setKeyMsg("ok", "✓ 已保存并自检通过：" + (t.detail || "") + capNote);
        toast("已保存为配置「" + body.name + "」（共 " + pv.providers.length + " 个），可在 ⚙ 高级设置 中查看 / 管理");
        renderKeyStatus();
      } else {
        setKeyMsg("err", "已保存，但自检未通过：" + humanTestError(t.detail || t.error || "请检查 Key 是否正确"));
        renderKeyStatus();
      }
    } catch (e) {
      setKeyMsg("err", "保存失败：" + humanTestError(e.message));
      renderKeyStatus(); // BUG-002 修复：保存/自检失败也要刷新状态条（provider 已保存则显示"待验证"黄态，避免停留在旧状态）
    } finally {
      els.btnKeySave.disabled = false;
    }
  });

  // 提示重置：用户一改动任何配置字段，立即清掉上次的结果提示（成功/失败都不残留）
  ["kpName", "kpUrl", "kpModel", "kpKey"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => setKeyMsg("", ""));
  });
  if (els.selPreset) els.selPreset.addEventListener("change", () => setKeyMsg("", ""));

  // 岗位名称：纯文本输入（T2 移除历史记录与下拉，仅保留格式指引与非法字符过滤）

  // ---------- 简历上传 ----------
  async function onResumeFile(file) {
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    if (!["pdf", "docx", "txt", "md", "text"].includes(ext)) {
      if (ext === "doc") toast("暂不支持旧版 .doc：请用 Word 打开后「另存为」.docx 或 .txt 再上传（约 1 分钟）");
      else toast("不支持格式：" + ext + "（支持 pdf / docx / txt / md）");
      return;
    }
    state.resume = { name: file.name, ext, dataUrl: null, text: null };
    els.fileMeta.style.display = "flex";
    els.fileInfo.textContent = file.name + "（" + (file.size / 1024).toFixed(1) + " KB）";
    els.fileParseState.textContent = "解析中…";
    els.resumePreview.style.display = "none";
    try {
      const dataUrl = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => rej(new Error("读取文件失败"));
        fr.readAsDataURL(file);
      });
      state.resume.dataUrl = dataUrl;
      const d = await api("/api/parse-resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resumeFile: dataUrl, resumeExt: ext })
      });
      state.resume.text = d.text;
      els.resumeNeedTip.style.display = "none";
      els.fileParseState.textContent = "✓ 已解析，" + d.meta.lines + " 行";
      els.fileParseState.style.color = "#059669";
      if (d.meta.suspectedScan) {
        els.fileParseState.textContent = "⚠ 解析内容很少（" + d.meta.lines + " 行），疑似扫描件/图片型 PDF——请上传文字版 PDF 或另存为 txt，否则生成的材料缺少你的项目经历";
        els.fileParseState.style.color = "#b45309";
      }
      els.resumePreview.textContent = d.text.slice(0, 600) + (d.text.length > 600 ? "\n…（已截断）" : "");
      els.resumePreview.style.display = "block";
    } catch (e) {
      state.resume = null;
      els.fileParseState.textContent = "✗ " + e.message;
      els.fileParseState.style.color = "#dc2626";
    }
  }
  els.dropResume.addEventListener("click", () => els.inpResume.click());
  els.inpResume.addEventListener("change", () => { if (els.inpResume.files[0]) onResumeFile(els.inpResume.files[0]); });
  els.dropResume.addEventListener("dragover", e => { e.preventDefault(); els.dropResume.classList.add("over"); });
  els.dropResume.addEventListener("dragleave", () => els.dropResume.classList.remove("over"));
  els.dropResume.addEventListener("drop", e => {
    e.preventDefault(); els.dropResume.classList.remove("over");
    if (e.dataTransfer.files[0]) onResumeFile(e.dataTransfer.files[0]);
  });
  els.btnRemoveFile.addEventListener("click", () => {
    state.resume = null;
    els.inpResume.value = "";
    els.fileMeta.style.display = "none";
    els.resumePreview.style.display = "none";
    els.resumeNeedTip.style.display = "";
  });

  // ---------- JD 读取 ----------
  els.btnFetchJd.addEventListener("click", async () => {
    const url = els.inpJdUrl.value.trim();
    if (!url) { toast("请先填写 JD 链接"); return; }
    if (!/^https?:\/\//i.test(url)) { toast("JD 链接格式不对：请填以 http:// 或 https:// 开头的完整网址"); return; }
    if (isLocalUrl(url)) { toast("该链接指向本机/内网地址，无法读取，请填写公网网址"); return; }
    els.btnFetchJd.disabled = true;
    els.btnFetchJd.textContent = "读取中…";
    try {
      const d = await api("/api/fetch-jd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) });
      els.inpJd.value = d.text;
      els.inpJdUrl.value = ""; // 读取成功后清空链接框：JD 文本与链接同时存在会触发"二选一"报错，此处直接规避
      toast("读取成功，已填充 JD 文本");
    } catch (e) {
      toast(e.message + "；建议直接粘贴 JD 文本（更准确）");
    } finally {
      els.btnFetchJd.disabled = false;
      els.btnFetchJd.textContent = "读取到下方";
    }
  });

  // JD 文本区粘贴图片拦截：提示用户贴文字而非截图（文本框无法承载图片，避免"粘贴了但没反应"的困惑）
  els.inpJd.addEventListener("paste", e => {
    const items = (e.clipboardData || {}).items;
    if (items) {
      for (const it of items) {
        if (it.type && it.type.startsWith("image/")) {
          e.preventDefault();
          toast("请粘贴 JD 文字而非图片：在招聘页面全选复制文字后粘贴；图片可用手机「识图转文字」转成文字再粘贴");
          return;
        }
      }
    }
  });

  // 前端本机/内网地址检测（与后端 fetch_jd.js isBlockedHost 同规则，输入时即提示，避免提交后才发现）
  function isLocalUrl(urlStr) {
    try {
      const u = new URL(urlStr);
      const h = u.hostname.toLowerCase();
      if (h === "localhost" || h.endsWith(".localhost") || h === "::1" || h.startsWith("::ffff:")) return true;
      const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
      if (m) {
        const a = +m[1], b = +m[2];
        if (a === 0 || a === 127 || a >= 224) return true;
        if (a === 10) return true;
        if (a === 169 && b === 254) return true;
        if (a === 172 && b >= 16 && b <= 31) return true;
        if (a === 192 && b === 168) return true;
      }
    } catch (e) {}
    return false;
  }

  // 岗位名称即时校验 + 非法字符直接拦截（与后端白名单一致：含 . / .. 及路径分隔符等即红框提示）
  // T11：非法字符在输入时直接被删除，从源头阻止「提交时报错」；无法删除的（如纯 . / ..）红框提示
  const ILLEGAL_CHARS = /[\\/:*?"<>|\u0000-\u001f]/g; // 用于 replace 的全局正则
  els.inpCompany.addEventListener("input", () => {
    const raw = els.inpCompany.value;
    if (/[\\/:*?"<>|\u0000-\u001f]/.test(raw)) {
      els.inpCompany.value = raw.replace(ILLEGAL_CHARS, "");
      els.inpCompany.title = "已自动移除非法字符（不能包含 \\ / : * ? \" < > | 等，它们会破坏文件名）";
      els.inpCompany.classList.add("err-inp");
      setTimeout(() => els.inpCompany.classList.remove("err-inp"), 1600);
    }
    if (els.inpCompany.value.length > 80) {
      els.inpCompany.value = els.inpCompany.value.slice(0, 80);
      els.inpCompany.title = "岗位名最长 80 字，超出部分已自动截断";
      els.inpCompany.classList.add("err-inp");
      setTimeout(() => els.inpCompany.classList.remove("err-inp"), 1600);
    }
    const v = els.inpCompany.value.trim();
    if (!v) { els.inpCompany.classList.remove("err-inp"); els.inpCompany.title = ""; return; }
    if (/^(\.{1,2})$/.test(v) || !/^[^\\\/:*?"<>|\u0000-\u001f]{1,80}$/.test(v)) {
      els.inpCompany.classList.add("err-inp");
      els.inpCompany.title = "岗位名不能是 . 或 ..，长度 ≤ 80";
    } else { els.inpCompany.classList.remove("err-inp"); els.inpCompany.title = ""; }
  });

  // ---------- 补充参考网址（动态行：每行一个输入框，"＋"新增一行） ----------
  function addUrlRow(focus) {
    // 最多 15 条（与后端 /api/material 校验、流水线 MAX_URL_COUNT 一致）
    if (els.urlRows.querySelectorAll(".url-row").length >= 15) {
      toast("参考网址最多 15 条", 2000);
      return;
    }
    const row = document.createElement("div");
    row.className = "row url-row";
    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "grow url-inp";
    inp.id = "urlInp";
    inp.placeholder = "https://...（http(s):// 开头，如牛客面经帖 / 公司官网 / 技术博客）";
    // 失焦即时校验：非法 URL / 本机内网地址红框提示，避免最后提交才报错
    inp.addEventListener("blur", () => {
      const v = inp.value.trim();
      if (v && !/^https?:\/\//i.test(v)) { inp.classList.add("err-inp"); inp.title = "网址需以 http:// 或 https:// 开头"; }
      else if (v && isLocalUrl(v)) { inp.classList.add("err-inp"); inp.title = "该链接指向本机/内网地址，无法读取，请填写公网网址"; }
      else { inp.classList.remove("err-inp"); inp.title = ""; }
    });
    const del = document.createElement("button");
    del.className = "rm url-del";
    del.title = "移除该行";
    del.textContent = "✕";
    del.addEventListener("click", () => {
      if (els.urlRows.querySelectorAll(".url-row").length > 1) { row.remove(); }
      else { inp.value = ""; }
    });
    inp.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); addUrlRow(); }
    });
    row.appendChild(inp);
    row.appendChild(del);
    els.urlRows.appendChild(row);
    if (focus !== false) inp.focus();
  }
  els.btnAddUrlRow.addEventListener("click", () => addUrlRow());
  addUrlRow(false); // 初始默认一行（行为与动态行完全一致：多行时 ✕ 删除，仅剩 1 行时 ✕ 清空）
  // 补充参考信息：实时字数计数（20,000 字上限，超限红框警告，避免用户无感知丢失长文本）
  const REF_INFO_MAX = 20000;
  els.inpRefInfo.addEventListener("input", () => {
    const n = els.inpRefInfo.value.length;
    els.refInfoCount.textContent = n.toLocaleString() + " / 20,000 字";
    els.refInfoCount.style.color = n > REF_INFO_MAX ? "var(--err)" : "var(--muted)";
    els.inpRefInfo.classList.toggle("err-inp", n > REF_INFO_MAX);
    els.inpRefInfo.title = n > REF_INFO_MAX ? "已超过 20,000 字上限，提交时超出部分会被截断" : "";
  });
  // 收集所有非空、合法的参考网址
  function collectUrls() {
    const urls = [];
    let bad = null;
    els.urlRows.querySelectorAll(".url-inp").forEach(inp => {
      const u = inp.value.trim();
      if (!u) return;
      if (!/^https?:\/\//i.test(u)) { bad = u + "（网址需以 http(s):// 开头）"; return; }
      if (isLocalUrl(u)) { bad = u + "（指向本机/内网地址，无法读取）"; return; }
      if (!urls.includes(u)) urls.push(u);
    });
    return { ok: !bad, urls: urls, bad: bad };
  }

  // ---------- 行业预设搜索分区 ----------
  async function loadZones() {
    try {
      const d = await api("/api/search-zones");
      d.zones.forEach(z => {
        const opt = document.createElement("option");
        opt.value = z.id;
        opt.textContent = z.name;
        els.selZone.appendChild(opt);
      });
      els.selZone.addEventListener("change", () => {
        const z = d.zones.find(x => x.id === els.selZone.value);
        els.zoneHint.textContent = z ? "常用检索：" + z.sites.join(" / ") : "";
      });
    } catch (e) { /* 忽略 */ }
  }

  // ---------- 任务 ----------
  function renderFileList() {
    els.fileList.innerHTML = FILE_NAMES.map(n => {
      const st = state.fileStatus[n] || "idle";
      const mark = st === "done" ? '<span class="st done">✓</span>'
        : st === "failed" ? '<span class="st failed">✗</span>'
        : st === "running" ? '<span class="st running"><span class="spin"></span></span>'
        : '<span class="st idle">·</span>';
      return '<div class="file-row"><span class="nm">' + n + '.md</span>' + mark + "</div>";
    }).join("");
  }
  function appendLog(text) {
    state.log.push(text);
    const div = document.createElement("div");
    div.textContent = text;
    els.logBox.appendChild(div);
    els.logBox.scrollTop = els.logBox.scrollHeight;
  }
  function onTaskEvent(evt) {
    if (evt.type === "step") {
      const map = { pending: ["run", "排队中…"], parsing: ["run", "解析简历…"], fetching: ["run", "读取网址…"],
        generating: ["run", "生成中…"], building: ["run", "渲染 HTML…"], verifying: ["run", "结构校验…"],
        reviewing: ["run", "质量审核…"], rework: ["run", "回炉重写…"],
        checking: ["run", "内容审核…"], cancelled: ["warn", "已取消"], error: ["fail", "失败"] };
      const m = map[evt.name];
      if (m) setBadge(els.taskBadge, m[0], m[1]);
      else if (/failed$/.test(evt.name)) setBadge(els.taskBadge, "fail", evt.name);
      else if (/done$/.test(evt.name)) {
        setBadge(els.taskBadge, "ok", evt.name.replace("-done", "") + " ✓");
        // 阶段完成：进度条推进到该阶段权重（R3）
        const base = evt.name.replace("-done", "");
        if (STEP_WEIGHTS[base] !== undefined) setProgress(STEP_WEIGHTS[base]);
      }
      // 阶段开始：进度条推进到该阶段权重（R3）
      if (evt.status === "running" && STEP_WEIGHTS[evt.name] !== undefined) setProgress(STEP_WEIGHTS[evt.name]);
    } else if (evt.type === "file") {
      state.fileStatus[evt.name] = evt.status;
      renderFileList();
      // 生成阶段按文件完成数推进（8 文件均分 20%→88% 区段，R3）
      if (evt.status === "done") {
        const doneCount = FILE_NAMES.filter(n => state.fileStatus[n] === "done").length;
        setProgress(Math.min(88, 20 + 68 * doneCount / FILE_NAMES.length));
      }
    } else if (evt.type === "log") {
      appendLog(evt.text);
    } else if (evt.type === "done") {
      setProgress(100, "完成");
      state.previewUrl = evt.previewUrl || null; // D4：供重试重建成功后刷新预览用
      finishTask(evt);
    } else if (evt.type === "build") {
      // D4：单文件重试后服务端重跑 build——重建成功即刷新结果区预览（此前会一直停在"未生成结果页"）
      if (evt.ok && state.company) {
        const u = "/preview/" + encodeURIComponent(state.company) + "/" + encodeURIComponent(state.company) + "面试准备.html";
        els.previewEmpty.style.display = "none";
        els.previewFrame.style.display = "block";
        els.previewFrame.src = u + "?t=" + Date.now();
        appendLog("✓ HTML 重建成功，结果页已刷新");
      } else {
        appendLog("✗ HTML 重建失败：" + (evt.detail || "未知原因"));
      }
    } else if (evt.type === "verify") {
      setBadge(els.verifyBadge, evt.ok ? "ok" : "fail", evt.ok ? "verify PASS" : "verify FAIL");
    } else if (evt.type === "error") {
      setBadge(els.taskBadge, "fail", "失败");
      appendLog("✗ " + (evt.text || "未知错误"));
      showResult(false, null);
      els.btnStart.disabled = false; // 任务失败后恢复生成按钮，允许修改参数重试
    } else if (evt.type === "needs-verify") {
      // v0.4.9：单文件重试后服务端重跑【待联网核实】清单，刷新结果区（可能新增/清除标记）
      const n = Array.isArray(evt.needsVerify) ? evt.needsVerify.reduce((s, x) => s + (x.items ? x.items.length : 0), 0) : 0;
      appendLog(n > 0
        ? "⚠ 更新【待联网核实】清单：当前 " + n + " 处待核实项（请核对来源后使用）"
        : "✓ 【待联网核实】清单已清空（当前产物无待核实标记）");
      renderVerifyBox(state.lastCheck, state.lastCheckOutput, evt.needsVerify);
    } else if (evt.type === "review") {
      // M3：质量回路每文件每轮裁决——更新面板并即时渲染
      state.qualityByFile[evt.file] = { round: evt.round, verdict: evt.verdict, source: evt.source, issues: evt.issues || [] };
      renderQualityBox();
    }
  }
  function connectSSE(taskId) {
    if (state.es) state.es.close();
    state.es = new EventSource("/api/task/" + taskId + "/events");
    state.es.onmessage = () => {};
    ["step", "file", "log", "done", "error", "build", "verify", "needs-verify", "review"].forEach(t => {
      state.es.addEventListener(t, e => { try { onTaskEvent(JSON.parse(e.data)); } catch (err) { /* ignore */ } });
    });
    state.es.onerror = () => { /* 服务端终态会主动关闭，浏览器会自动重连；任务结束后手动 close */ };
  }
  // M3：质量回路审核面板——每文件轮次/裁决/来源/遗留问题；REVISE 或回炉上限用尽可强制回炉
  function renderQualityBox() {
    const sum = state.qualitySummary;
    const live = Object.keys(state.qualityByFile).map(k => state.qualityByFile[k]);
    const merged = {};
    if (sum) sum.forEach(s => { merged[s.file] = Object.assign({}, merged[s.file], s); });
    live.forEach(r => { merged[r.file] = Object.assign({}, merged[r.file], r); });
    const files = Object.keys(merged);
    if (!files.length) { els.qualityBox.style.display = "none"; return; }
    els.qualityBox.style.display = "block";
    const rows = files.map(f => {
      const m = merged[f];
      const verdict = m.verdict || "PASS";
      const color = verdict === "PASS" ? "var(--ok)" : "var(--err)";
      const badge = verdict === "PASS" ? "✓ PASS" : "✗ REVISE";
      const srcTxt = m.source === "rule" ? "规则" : m.source === "llm" ? "LLM" : "—";
      const rounds = m.rounds !== undefined ? m.rounds + " 轮" : m.round !== undefined ? (m.round + 1) + " 轮" : "—";
      const remain = m.remaining > 0
        ? '<span style="color:var(--warn)">（遗留 ' + m.remaining + ' 项待处理）</span>' : "";
      const issues = (m.issues || []).slice(0, 3).map(i =>
        '<div style="font-size:12px;color:var(--ink-soft);margin-left:16px">· [' + i.code + "/" + i.severity + "] " +
        String(i.item || "").replace(/</g, "&lt;") + "</div>").join("");
      const busy = !!state.qualityBusy[f];
      const btn = (verdict === "REVISE" || (busy && state.qualityBusy[f].reworkable))
        ? '<button class="btn ghost sm qrework" data-name="' + f + '"' + (busy ? " disabled" : "") + '>' +
          (busy ? "回炉中…" : "回炉重写") + "</button>"
        : "";
      return '<div class="file-row" style="align-items:flex-start">' +
        '<span class="nm" style="padding-top:3px">' + f + '.md</span>' +
        '<span class="mini" style="color:' + color + ';font-weight:600;padding-top:3px">' + badge + "</span>" +
        '<span class="mini" style="color:var(--ink-mute);padding-top:3px">' + srcTxt + " · " + rounds + "</span>" +
        btn +
        '<div style="flex:1;min-width:0">' + issues + remain + "</div></div>";
    }).join("");
    els.qualityBox.innerHTML =
      '<div class="hint-line" style="margin:0 0 8px"><span style="font-weight:600">质量回路审核（M3）</span>' +
      '<span class="mini" style="color:var(--ink-mute)">规则 + LLM 双闸门，REVISE 已带意见回炉</span></div>' + rows;
    els.qualityBox.querySelectorAll(".qrework").forEach(b => b.addEventListener("click", () => reworkFile(b.dataset.name)));
  }
  async function reworkFile(name) {
    if (!state.taskId) return;
    state.qualityBusy[name] = { reworkable: true };
    renderQualityBox();
    try {
      const r = await api("/api/task/" + state.taskId + "/rework-file", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name })
      });
      if (r.ok) {
        appendLog("✓ " + name + " 强制回炉完成（verdict=" + r.verdict + "）");
        if (r.verdict === "REVISE") appendLog("⚠ " + name + " 回炉上限用尽仍 REVISE（遗留 " + r.remaining + " 项，建议人工复核）");
        // 回炉后服务端已重跑 build/verify/check；用 review 事件刷新本文件裁决
        if (r.rounds && r.rounds.length) {
          const last = r.rounds[r.rounds.length - 1];
          state.qualityByFile[name] = { round: last.round, verdict: last.verdict, source: last.source, issues: last.issues || [] };
        }
      } else {
        appendLog("✗ " + name + " 强制回炉失败：" + (r.error || "未知错误"));
      }
    } catch (e) {
      appendLog("✗ " + name + " 强制回炉异常：" + e.message);
    } finally {
      delete state.qualityBusy[name];
      renderQualityBox();
    }
  }
  // 渲染结果区的内容审核 + 联网核实清单（v0.4.9 代码审查修复：从 showResult 抽取，
  // 供单文件重试后的 needs-verify 事件复用刷新，保证清单与产物一致）
  function renderVerifyBox(check, checkOutput, needsVerify) {
    const hasCheck = check !== undefined && check !== null;
    const hasVerify = needsVerify && needsVerify.length;
    if (hasCheck || hasVerify) {
      els.checkBox.style.display = "block";
      const pass = check === true;
      els.checkBox.className = "check-box" + (pass ? "" : " warn");
      let html = "";
      if (hasCheck) {
        html +=
          '<div class="hint-line" style="margin:0 0 10px">' +
          (pass
            ? '<span style="color:var(--ok)">✓ 内容审核通过（PASS）</span>'
            : '<span style="color:var(--warn)">⚠ 内容审核告警（建议修正后重新生成）</span>') +
          (checkOutput
            ? '<pre style="white-space:pre-wrap;font-size:12px;max-height:180px;overflow:auto;margin-top:8px;color:var(--ink-soft)">' +
              String(checkOutput).replace(/</g, "&lt;") + "</pre>"
            : "") +
          "</div>";
      }
      if (hasVerify) {
        const lines = needsVerify.map(v =>
          '<div style="margin:2px 0"><b>' + String(v.file).replace(/</g, "&lt;") + '</b>：' +
          v.items.map(q => '<span style="color:var(--warn)">' + String(q).replace(/</g, "&lt;") + '</span>').join('；') + '</div>'
        ).join("");
        html +=
          '<div class="hint-line" style="margin:0">' +
          '<span style="color:var(--warn)">⚠ ' + needsVerify.length + ' 个文件含【待联网核实】项（AI 未确认的时效信息，请核对来源后使用）</span>' +
          '<div style="margin-top:8px;font-size:12px;color:var(--ink-soft)">' + lines + '</div>' +
          "</div>";
      }
      els.checkBox.innerHTML = html;
    } else {
      els.checkBox.style.display = "none";
    }
  }
  function showResult(ok, evt) {
    els.cardResult.style.display = "block";
    setBadge(els.verifyBadge, ok ? "ok" : "fail", ok ? "verify PASS" : "verify FAIL / 部分失败");
    // 生成成功 → 顶部提示明确结果文件的完整保存路径（用户找文件的关键）
    // 注意：不能用 alert() 同步弹窗——Trae 内置浏览器不支持，会阻塞主线程导致整页/IDE 卡死
    if (ok && evt && evt.resultPath) {
      setTimeout(() => {
        toast("✅ 面试材料已生成！文件已保存到：" + evt.resultPath + "（也可在下方预览窗口中阅读）", 9000);
      }, 300);
    }
    if (evt && evt.previewUrl) {
      els.previewEmpty.style.display = "none";
      els.previewFrame.style.display = "block";
      els.previewFrame.src = evt.previewUrl;
    } else {
      // D4 修复：build 失败时服务端不再下发 previewUrl——结果区显示中文指引，不再出现英文 Not Found
      els.previewEmpty.style.display = "block";
      els.previewFrame.style.display = "none";
      els.previewEmpty.textContent = ok
        ? "结果页预览：请点击下方文件列表中的 HTML 文件名打开"
        : "未生成结果页（生成或渲染失败）：请查看上方日志定位原因，并对失败文件点「重试」";
    }
    // 内容审核结果（LLM 对照基准的审核，check: true=通过 false=告警 null=未执行）
    // + 联网核实清单（v0.4.9）：生成文件标注的【待联网核实】时效信息项，提示人工核对来源
    // 渲染复用 renderVerifyBox；记录最近一次 check 结果，供 retry 后的 needs-verify 事件刷新时保留审核区块
    state.lastCheck = evt && evt.check;
    state.lastCheckOutput = evt && evt.checkOutput;
    renderVerifyBox(evt && evt.check, evt && evt.checkOutput, evt && evt.needsVerify);
    // M3：质量回路汇总（done 事件携带全部白名单文件审核结果）
    state.qualitySummary = evt && evt.qualitySummary ? evt.qualitySummary : state.qualitySummary;
    renderQualityBox();
    // 重试区：列出失败文件
    const failed = FILE_NAMES.filter(n => state.fileStatus[n] === "failed");
    if (failed.length) {
      els.retryArea.style.display = "flex";
      els.retryArea.innerHTML = '<span style="font-size:12.5px;color:var(--ink-soft)">失败文件可重试：</span>' +
        failed.map(n => '<button class="btn ghost sm retry" data-name="' + n + '">重试 ' + n + '</button>').join("");
      els.retryArea.querySelectorAll(".retry").forEach(b => b.addEventListener("click", () => retryFile(b.dataset.name)));
    } else {
      els.retryArea.style.display = "none";
    }
  }
  function finishTask(evt) {
    if (state.es) { state.es.close(); state.es = null; }
    setBadge(els.taskBadge, "ok", "完成");
    if (window.stepUI) { stepUI(2, "done"); stepUI(3, "done"); }
    setRailNote(evt.ok ? "完成：结果已生成，可在下方预览 / 打印 / 分享" : "部分完成：失败文件可单独重试");
    showResult(!!evt.ok, evt);
    els.btnStart.disabled = false; // 任务完成后恢复生成按钮（此前永久禁用，需刷新页面才能重新生成）
    // 完成后引导：自动滚动到结果卡并提示下一步
    try {
      els.cardResult.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { /* 忽略滚动失败 */ }
    if (evt.ok) {
      toast("✅ 材料已生成！可滚动到下方预览 / 打印 / 分享；如单份失败可点「重试」", 6000);
    } else {
      toast("生成部分完成：可看结果区说明，失败项可单独重试", 6000);
    }
  }
  async function retryFile(name) {
    if (!state.taskId) return;
    appendLog("重试生成 " + name + ".md ...");
    try {
      const r = await api("/api/task/" + state.taskId + "/retry-file", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name })
      });
      if (r.ok) {
        appendLog("重试成功，已重新构建 HTML（build " + (r.build ? "✓" : "✗") + " / verify " + (r.verify ? "✓" : "✗") + "）");
        toast("重试成功，产物已更新");
      } else {
        appendLog("✗ " + (r.error || "重试失败"));
      }
    } catch (e) { appendLog("✗ " + e.message); }
  }

  els.btnStart.addEventListener("click", async () => {
    els.inputError.textContent = "";
    // 一键生成前先校验：必须有可用的文本模型 Key（第 1 步就绪）
    let providers = [];
    try { providers = (await api("/api/providers")).providers; state.providers = providers; } catch (e) { providers = []; }
    const hasTextKey = providers.some(p => p.enabled && p.hasKey && (p.cap || []).includes("text"));
    if (!hasTextKey) {
      els.inputError.textContent = "还没有可用的 API Key：请先在顶部第 1 步选厂商、选模型、填 Key，点「保存并自检」";
      els.cardApiKey.scrollIntoView({ behavior: "smooth", block: "center" });
      els.cardApiKey.classList.add("flash");
      setTimeout(() => els.cardApiKey.classList.remove("flash"), 2600);
      renderKeyStatus();
      return;
    }
    const company = els.inpCompany.value.trim();
    state.company = company; // D4：重试重建成功后据此计算结果页预览地址
    const jdText = els.inpJd.value.trim();
    const jdUrl = els.inpJdUrl.value.trim();
    // R9 必填项集中校验：红字指出缺失项 + 定位到第一个缺失字段（滚动到可视区并红框高亮，让用户一眼看到该改哪）
    const missing = [];
    if (!company) missing.push("岗位名称");
    if (!state.resume || !state.resume.dataUrl) missing.push("简历上传");
    if (!jdText && !jdUrl) missing.push("岗位 JD 文本（或链接）");
    if (missing.length) {
      els.inputError.textContent = "必填项未填写：" + missing.join("、") + "——已定位到第一个缺失项";
      let firstMissing = null;
      if (!company) firstMissing = els.inpCompany;
      else if (!state.resume || !state.resume.dataUrl) firstMissing = els.dropResume;
      else firstMissing = els.inpJd;
      if (firstMissing) {
        firstMissing.classList.add("err-inp");
        try { firstMissing.scrollIntoView({ behavior: "smooth", block: "center" }); } catch (e) {}
        setTimeout(() => firstMissing.classList.remove("err-inp"), 2200);
      }
      if (missing.includes("简历上传")) els.resumeNeedTip.style.display = "";
      return;
    }
    // 与后端白名单一致：岗位名会作为文件名/目录名，禁止路径分隔符与非法字符（避免提交后才报错）
    if (!/^(?!\.{1,2}$)[^\\\/:*?"<>|\u0000-\u001f]{1,80}$/.test(company)) {
      els.inputError.textContent = "岗位名不能包含 \\ / : * ? \" < > | 等字符，也不能是 . 或 ..，且不超过 80 字";
      return;
    }
    // JD 文本与链接同时存在时以文本优先（链接读取成功后已清空链接框，此分支仅兜底手动填写场景）

    const body = { company };
    if (state.resume && state.resume.dataUrl) {
      body.resumeFile = state.resume.dataUrl;
      body.resumeExt = state.resume.ext;
    }
    if (jdText) body.jdText = jdText; else body.jdUrl = jdUrl;
    const urlRes = collectUrls();
    if (!urlRes.ok) { els.inputError.textContent = "参考网址需以 http(s):// 开头：" + urlRes.bad; return; }
    if (urlRes.urls.length) body.urls = urlRes.urls;
    // 补充参考信息：超过 20,000 字时后端会截断，此处仅在前端给出明确警告（不阻断，用户可继续）
    const refInfo = els.inpRefInfo.value.trim();
    if (refInfo) body.refInfo = refInfo;

    els.btnStart.disabled = true;
    els.cardProcess.style.display = "block";
    els.cardResult.style.display = "none";
    els.cardResult.querySelector("#previewEmpty").textContent = "等待生成完成…";
    els.previewEmpty.style.display = "block";
    els.previewFrame.style.display = "none";
    state.fileStatus = {}; state.log = [];
    state.qualityByFile = {}; state.qualitySummary = null; state.qualityBusy = {};
    FILE_NAMES.forEach(n => { state.fileStatus[n] = "idle"; });
    els.logBox.innerHTML = "";
    renderFileList();
    setBadge(els.taskBadge, "run", "提交中…");
    if (window.stepUI) stepUI(2, "active");
    setRailNote("生成中：8 份材料依次生成，进度见下方进度条");

    try {
      const d = await api("/api/material", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      state.taskId = d.taskId;
      connectSSE(d.taskId);
      toast("任务已创建：" + d.taskId);
    } catch (e) {
      setBadge(els.taskBadge, "fail", "创建失败");
      els.inputError.textContent = e.message;
      els.btnStart.disabled = false;
    }
  });

  els.btnCancel.addEventListener("click", async () => {
    if (!state.taskId) return;
    try { await api("/api/task/" + state.taskId + "/cancel", { method: "POST" }); }
    catch (e) { toast(e.message); }
    els.btnStart.disabled = false;
  });

  // ---------- Provider 设置 ----------
  // 验证状态持久化：只有「保存并自检」真实请求通过后才显示绿色；否则显示"待验证"（避免配置残留造成误报）
  // BUG-001 修复（v0.4.18）：verified 记录绑定 Key 指纹（apiKeyMasked 后 4 位）——
  //   换 Key 后指纹不匹配自动失效，杜绝「旧验证标记 + 新假 Key」仍显示绿色"已就绪"的假阳性
  function getVerified() {
    try { return JSON.parse(localStorage.getItem("msa_verified") || "{}"); } catch (e) { return {}; }
  }
  function markVerified(name) {
    try {
      const p = (state.providers || []).find(x => x.name === name);
      const k = p && p.apiKeyMasked ? String(p.apiKeyMasked).slice(-4) : "";
      const v = getVerified(); v[name] = { t: Date.now(), k }; localStorage.setItem("msa_verified", JSON.stringify(v));
    } catch (e) {}
  }
  // 主页面第 1 步的状态条：四态（绿✓=已自检通过 / 黄⚠=待验证 / 黄⚙=缺文本能力 / 蓝ℹ=未配置引导）——颜色+图标双编码（v0.4.17）
  function renderKeyStatus() {
    let providers = [];
    try { providers = state.providers || []; } catch (e) {}
    const verified = getVerified();
    const usable = providers.filter(p => p.enabled && p.hasKey && (p.cap || []).includes("text"));
    // BUG-001：仅认可「新格式（对象 + 指纹）且指纹与当前 Key 后 4 位一致」的验证记录；旧数字格式/指纹不匹配一律视为未验证
    const verifiedUsable = usable.filter(p => {
      const v = verified[p.name];
      return v && typeof v === "object" && v.k && v.k === (p.apiKeyMasked || "").slice(-4);
    });
    if (verifiedUsable.length) {
      els.keyStatus.className = "key-status ok";
      els.keyStatus.innerHTML = "✓ API Key 已配置成功，共 " + verifiedUsable.length + " 个可用（模型：" +
        verifiedUsable.map(p => p.displayName || p.model).join("、") + "）。状态正常。下一步：填写下方第 2 步内容（岗位 / 简历 / JD），点「🚀 一键生成面试材料」。";
      if (window.stepUI) stepUI(1, "done");
      setRailNote("下一步：第 2 步 填写岗位 / 简历 / JD → 点「🚀 一键生成」");
    } else if (usable.length) {
      els.keyStatus.className = "key-status warn";
      els.keyStatus.innerHTML = "⚠ 已保存 " + usable.length + " 个配置，但<b>尚未验证真实可用</b>。请点「💾 保存并自检」完成验证（通过后状态条变绿）；若失败，请按提示核对 API Key / Base URL / 模型名。";
    } else if (providers.length) {
      els.keyStatus.className = "key-status warn";
      els.keyStatus.innerHTML = "⚙ 已保存 " + providers.length + " 个 Key，但均<b>缺少文本生成能力</b>（cap 需含 text）。生成面试材料必须有文本模型，请重新点「💾 保存并自检」。";
    } else {
      els.keyStatus.className = "key-status info";
      els.keyStatus.innerHTML = "ℹ 尚未配置 API Key，目前无法生成材料。请按上方引导：「🔑 第 1 步」①选厂商 → ②选模型 → ③粘贴 Key → 点「💾 保存并自检」，状态条变绿即完成。";
    }
  }
  async function loadProviders() {
    try {
      const d = await api("/api/providers");
      state.providers = d.providers;
      const usable = d.providers.filter(p => p.enabled && p.hasKey && (p.cap || []).includes("text"));
      els.provStatus.textContent = "provider " + usable.length + " 可用";
      renderProviders(d.providers);
      renderKeyStatus();
    } catch (e) {
      els.provStatus.textContent = "provider 加载失败";
      els.keyStatus.className = "key-status err";
      els.keyStatus.innerHTML = "⚠ 无法读取配置：" + e.message;
    }
  }
  function renderProviders(list) {
    if (!list.length) { els.provList.innerHTML = '<div class="hint-line">暂无 provider，请在下方新增。</div>'; return; }
    els.provList.innerHTML = list.map(p => {
      const caps = (p.cap || []).join("/") || "all";
      return '<div class="prov-item">' +
        '<div class="pname">' + (p.displayName || p.name) +
          '<button class="toggle ' + (p.enabled ? "on" : "") + '" data-name="' + p.name + '" data-on="' + p.enabled + '" title="启停"></button>' +
        "</div>" +
        '<div class="pmeta">' + p.model + "<br>" + p.baseUrl + "<br>key: " + (p.apiKeyMasked || "（未设置）") + " · caps: " + caps +
          (p.maxOutputTokens ? " · max " + p.maxOutputTokens : "") + "</div>" +
        '<div class="pact">' +
          '<button class="btn ghost sm" data-act="test" data-name="' + p.name + '">自检</button>' +
          '<button class="btn danger sm" data-act="del" data-name="' + p.name + '">删除</button>' +
          '<span class="mini" id="pt-' + p.name + '"></span>' +
        "</div></div>";
    }).join("");
    els.provList.querySelectorAll(".toggle").forEach(b => b.addEventListener("click", async () => {
      try {
        const d = await api("/api/providers", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: b.dataset.name, enabled: b.dataset.on !== "true" }) });
        renderProviders(d.providers);
        toast("已切换启停");
      } catch (e) { toast(e.message); }
    }));
    els.provList.querySelectorAll('[data-act="del"]').forEach(b => b.addEventListener("click", async () => {
      // 不用 confirm() 同步弹窗（Trae 内置浏览器不支持，会阻塞主线程导致整页/IDE 卡死）：
      // 直接删除，通过顶部 toast 给出确认反馈
      try {
        const d = await api("/api/providers/" + encodeURIComponent(b.dataset.name), { method: "DELETE" });
        state.providers = d.providers; // BUG-003 修复：删除后同步 state + 刷新主状态条，避免停留在旧状态
        renderProviders(d.providers);
        renderKeyStatus();
        // 同步清理该 provider 的验证标记，避免残留记录与"已删除"状态冲突
        try { const v = getVerified(); if (v[b.dataset.name]) { delete v[b.dataset.name]; localStorage.setItem("msa_verified", JSON.stringify(v)); } } catch (e2) {}
        toast("已删除 provider「" + b.dataset.name + "」");
      } catch (e) { toast(e.message); }
    }));
    els.provList.querySelectorAll('[data-act="test"]').forEach(b => b.addEventListener("click", async () => {
      const el = els.provList.querySelector("#pt-" + b.dataset.name);
      el.textContent = "自检中…";
      el.className = "mini";
      try {
        // P3-1 修复：抽屉"自检"改为真实最小请求（real:true），"✓ 可用"必须真实连通；原 {} 仅配置校验会误报
        const d = await api("/api/providers/" + encodeURIComponent(b.dataset.name) + "/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"real":true}' });
        if (d.ok) markVerified(b.dataset.name);
        el.textContent = d.ok ? "✓ 可用" : "✗ " + (d.detail || d.error || "不可用");
        el.className = "mini " + (d.ok ? "ok" : "err");
      } catch (e) {
        el.textContent = "✗ " + e.message;
        el.className = "mini err";
      }
    }));
  }
  els.btnSaveProvider.addEventListener("click", async () => {
    const p = { name: els.pName.value.trim(), baseUrl: els.pUrl.value.trim(), model: els.pModel.value.trim(),
      apiKey: els.pKey.value.trim(), cap: els.pCap.value.split(",").map(s => s.trim()).filter(Boolean) };
    // 字段级校验：逐个指出缺什么
    const missing = [];
    if (!p.name) missing.push("配置名称");
    if (!p.baseUrl) missing.push("Base URL");
    if (!p.model) missing.push("模型名");
    if (missing.length) { els.provMsg.textContent = "缺少必填项：" + missing.join("、") + "（可参照上方已保存列表的格式填写）"; els.provMsg.className = "mini err"; return; }
    if (!/^https?:\/\//i.test(p.baseUrl)) { els.provMsg.textContent = "Base URL 需以 http:// 或 https:// 开头（如 https://api.xxx.com/v1/chat/completions）"; els.provMsg.className = "mini err"; return; }
    try {
      const d = await api("/api/providers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
      els.provMsg.textContent = "已保存 ✓（可在主页面状态条确认）";
      els.provMsg.className = "mini ok";
      toast("已保存配置「" + p.name + "」，共 " + d.providers.length + " 个");
      resetProviderForm();
      loadProviders(); // 内部会重绘列表 + 刷新状态条（避免双重渲染）
    } catch (e) { els.provMsg.textContent = humanTestError(e.message); els.provMsg.className = "mini err"; }
  });
  // 保存后清空表单，恢复到「新增」状态（避免残留上一次的输入造成误解）
  function resetProviderForm() {
    els.pName.value = ""; els.pUrl.value = ""; els.pModel.value = ""; els.pKey.value = "";
    els.pCap.value = "text";
  }
  // 提示重置：改动表单字段即清掉上次提示
  ["pName", "pUrl", "pModel", "pKey", "pCap"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => { els.provMsg.textContent = ""; els.provMsg.className = "mini"; });
  });
  els.btnTestProvider.addEventListener("click", async () => {
    const name = els.pName.value.trim();
    if (!name) { els.provMsg.textContent = "请先填写配置名称（仅用于标识，可任取）；再点「保存」或填 Key 后自检"; els.provMsg.className = "mini err"; return; }
    els.provMsg.textContent = "自检中…（真实最小请求，需 key 有效）";
    els.provMsg.className = "mini";
    try {
      const d = await api("/api/providers/" + encodeURIComponent(name) + "/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"real":true}' });
      if (d.ok) markVerified(name); // 抽屉内自检通过同样记录验证状态
      els.provMsg.textContent = (d.ok ? "✓ " : "✗ ") + (d.detail || "");
      els.provMsg.className = "mini " + (d.ok ? "ok" : "err");
    } catch (e) { els.provMsg.textContent = "✗ " + e.message; els.provMsg.className = "mini err"; }
  });

  // ---------- 本地 CLI 工具（P0 适配层：探测 markitdown/mineru/rapidocr 等） ----------
  async function loadCliTools() {
    try {
      const d = await api("/api/cli-tools");
      renderCliTools(d.tools || []);
      els.cliToolsMsg.textContent = "";
    } catch (e) {
      els.cliToolsMsg.textContent = "探测失败：" + e.message;
    }
  }
  function renderCliTools(tools) {
    if (!tools.length) { els.cliToolsList.innerHTML = '<div class="hint-line">无可用工具信息。</div>'; return; }
    els.cliToolsList.innerHTML = tools.map(t => {
      const status = t.found
        ? '<span style="color:#059669;font-weight:600">✓ 已安装</span><br><span class="mini">' + t.binPath + '</span>'
        : '<span style="color:#b45309;font-weight:600">✗ 未安装</span><br><span class="mini">安装：<code>' + t.install + '</code></span>';
      return '<div class="prov-item"><div class="pname">' + t.id + '</div>' +
        '<div class="pmeta">' + t.desc + '</div>' +
        '<div class="pact">' + status + '</div></div>';
    }).join("");
  }

  // ---------- 内置 OCR 引擎（纯文本版默认方案：onnxruntime-node + PP-OCRv4） ----------
  async function loadOcrEngine() {
    const el = els.ocrJsStatus;
    if (!el) return;
    el.innerHTML = '<span class="mini">检查中…</span>';
    try {
      const d = await api("/api/ocr-engine");
      const s = d.engine || {};
      if (s.ok) {
        el.innerHTML = '<span style="color:#059669;font-weight:600">✓ 就绪（默认方案，离线可用）</span><br><span class="mini">det ' + s.det + ' / rec ' + s.rec + ' / dict ' + s.dict + '；图片文字提取自动优先使用本引擎（无需视觉模型）</span>';
      } else {
        el.innerHTML = '<span style="color:#b45309;font-weight:600">✗ 模型缺失</span><br><span class="mini">缺少 ' +
          (s.det && s.det !== "缺失" ? "" : "det ") + (s.rec && s.rec !== "缺失" ? "" : "rec ") + (s.dict && s.dict !== "缺失" ? "" : "dict ") +
          '（应位于 20_执行/assets/ocr/，随仓库发布；缺失时自动回退本地 CLI OCR / 视觉模型）</span>';
      }
    } catch (e) {
      el.innerHTML = '<span style="color:#b45309;font-weight:600">✗ 引擎不可用</span><br><span class="mini">' + e.message + '（将回退本地 CLI OCR / 视觉模型）</span>';
    }
  }

  // ---------- 联网搜索（v0.4.9：可选增强，Tavily Key；AI 遇时效信息自动联网核实） ----------
  async function loadWebSearch() {
    try {
      const d = await api("/api/web-search");
      renderWebSearch(d);
      els.webSearchMsg.textContent = "";
    } catch (e) {
      els.webSearchMsg.textContent = "读取失败：" + e.message;
    }
  }
  function renderWebSearch(d) {
    const el = els.webSearchStatus;
    if (!el) return;
    if (d && d.configured) {
      el.innerHTML = '<span style="color:#059669;font-weight:600">✓ 已配置（' + (d.provider || "") + " " + (d.keyMasked || "") + '）</span><br><span class="mini">生成前自动搜索权威来源并注入上下文，遇时效信息联网核实，减少【待联网核实】标注。</span>';
      if (els.webSearchKey) els.webSearchKey.value = "";
    } else {
      el.innerHTML = '<span style="color:#b45309;font-weight:600">✗ 未配置</span><br><span class="mini">AI 将按协议在正文标注【待联网核实】并在结果页汇总清单；配置搜索 Key 后自动联网核实。</span>';
    }
  }
  if (els.btnSaveWebSearch) els.btnSaveWebSearch.addEventListener("click", async () => {
    try {
      const d = await api("/api/web-search", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: els.webSearchKey.value.trim(), provider: "tavily" })
      });
      renderWebSearch(d);
      els.webSearchMsg.textContent = d.configured ? "已保存" : "已关闭联网搜索";
      els.webSearchMsg.className = "mini" + (d.configured ? " ok" : "");
    } catch (e) {
      els.webSearchMsg.textContent = "保存失败：" + e.message;
    }
  });

  // ---------- 抽屉 ----------
  els.btnSettings.addEventListener("click", () => { els.drawer.classList.add("open"); els.mask.style.display = "block"; loadProviders(); loadCliTools(); loadOcrEngine(); loadWebSearch(); });
  els.btnCloseDrawer.addEventListener("click", closeDrawer);
  els.mask.addEventListener("click", closeDrawer);
  els.btnProbeCli.addEventListener("click", () => { loadCliTools(); });
  function closeDrawer() { els.drawer.classList.remove("open"); els.mask.style.display = "none"; }

  // ---------- 初始化 ----------
  loadZones();
  loadProviders();
})();
