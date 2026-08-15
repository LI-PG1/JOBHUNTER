// vision_analyze.js - Universal vision analysis script (OpenAI-compatible APIs)
// Usage: node vision_analyze.js <imagePath> "[prompt]"
// Config: 20_执行/config.json (providers array, order = priority)
//
// 纯文本版（面试准备助手）视觉链路（本地 OCR 优先）：
//   1. 本地 OCR（内置引擎 ocr_js.js：onnxruntime-node + PP-OCRv4 轻量模型，开箱即用、离线免费）
//   2. 本地 CLI OCR（cli_tools.js：rapidocr/paddleocr，本机装有 Python 的高级用户可选增强）
//   3. vision provider（多模态模型 API，仅作兜底：已配置视觉 key 时才可用）
// 效果：只需一个文本模型即可完整使用本版——图片 → 本地 OCR 提取文字 → 交给文本模型理解，
//       无需视觉模型；未配置视觉 key / 离线时本地 OCR 仍可用。
// 原则：各环节均为"可选增强"，任一环节缺失自动跳过，绝不阻塞主流程。
const fs = require("fs");
const path = require("path");
const https = require("https");

const CONFIG_PATH = path.join(__dirname, "config.json");
const REQUEST_TIMEOUT_MS = 30000; // 单 provider 30s 超时

// 惰性加载：内置 OCR / CLI OCR 缺失时返回 null，不影响主链路
let _ocrJs = null, _cliTools = null;
function loadOcrJs() {
  if (_ocrJs === null) {
    try { _ocrJs = require("./ocr_js.js"); } catch (e) { _ocrJs = { __err: e }; }
  }
  return _ocrJs && !_ocrJs.__err ? _ocrJs : null;
}
function loadCliTools() {
  if (_cliTools === null) {
    try { _cliTools = require("./cli_tools.js"); } catch (e) { _cliTools = { __err: e }; }
  }
  return _cliTools && !_cliTools.__err ? _cliTools : null;
}

function loadConfig() {
  const raw = fs.readFileSync(CONFIG_PATH, "utf8");
  const cfg = JSON.parse(raw);
  if (Array.isArray(cfg.providers)) return cfg.providers;
  // 兼容旧版单 provider 配置 {provider, apiKey, baseUrls, models}
  if (cfg.provider) {
    return [{
      name: cfg.provider,
      baseUrl: cfg.baseUrls && cfg.baseUrls[cfg.provider],
      model: cfg.models && cfg.models[cfg.provider],
      apiKey: cfg.apiKey,
      enabled: true
    }];
  }
  throw new Error("config.json 缺少 providers 数组");
}

// 按能力过滤 provider：cap 未设置视为兼容所有；视觉分析只要含 "vision" 的
function availableProviders(providers) {
  return providers.filter(p =>
    p && p.enabled && p.apiKey && p.apiKey.length > 10 && p.baseUrl && p.model &&
    (!p.cap || p.cap.indexOf("vision") >= 0)
  );
}

function makeDataUrl(imgPath) {
  const b64 = fs.readFileSync(imgPath).toString("base64");
  const ext = (path.extname(imgPath) || ".png").replace(".", "").toLowerCase();
  const mime = ext === "jpg" ? "jpeg" : ext;
  return "data:image/" + mime + ";base64," + b64;
}

// 返回 Promise<{ok, text?, error?}>
function callProvider(provider, dataUrl, prompt) {
  return new Promise((resolve) => {
    const body = JSON.stringify({
      model: provider.model,
      messages: [{
        role: "user",
        content: [
          { type: "text", text: prompt },
          { type: "image_url", image_url: { url: dataUrl } }
        ]
      }],
      max_tokens: 1024
    });

    let u;
    try { u = new URL(provider.baseUrl); }
    catch (e) { return resolve({ ok: false, error: "baseUrl 非法: " + provider.baseUrl }); }

    const req = https.request({
      host: u.host,
      path: u.pathname + u.search,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + provider.apiKey,
        "Content-Length": Buffer.byteLength(body)
      }
    }, res => {
      // 响应体收集用 Buffer 数组，end 时统一解码：
      // 直接 d += c 会在 chunked 传输把多字节汉字切成两块时，于块边界产生 U+FFFD 乱码（R5-乱码修复）
      const bufs = [];
      res.on("data", c => { bufs.push(c); });
      res.on("end", () => {
        const d = Buffer.concat(bufs).toString("utf8");
        const status = res.statusCode || 0;
        if (status < 200 || status >= 300) {
          return resolve({ ok: false, error: "HTTP " + status + ": " + d.slice(0, 400) });
        }
        try {
          const j = JSON.parse(d);
          if (j.error) return resolve({ ok: false, error: "API error: " + JSON.stringify(j.error) });
          const content = j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
          if (!content) return resolve({ ok: false, error: "响应无 content 字段" });
          resolve({ ok: true, text: content });
        } catch (e) {
          resolve({ ok: false, error: "响应解析失败: " + d.slice(0, 400) });
        }
      });
    });

    req.setTimeout(REQUEST_TIMEOUT_MS, () => {
      req.destroy(new Error("timeout after " + REQUEST_TIMEOUT_MS + "ms"));
    });
    req.on("error", e => resolve({ ok: false, error: "请求错误: " + e.message }));
    req.write(body);
    req.end();
  });
}

// ---------- 本地 OCR（内置引擎 > CLI OCR，不触网、不花钱） ----------
async function extractTextLocal(imgPath) {
  const errors = [];
  const ocrJs = loadOcrJs();
  if (ocrJs) {
    try {
      if (ocrJs.checkEngine && ocrJs.checkEngine().ok) {
        const r = await ocrJs.ocrImage(imgPath);
        if (r.ok && r.text && r.text.trim()) {
          return { ok: true, text: r.text.trim(), lines: r.lines || [], engine: "内置OCR", ms: r.ms };
        }
        errors.push("内置OCR：无识别结果");
      } else {
        errors.push("内置OCR：模型缺失（assets/ocr/）");
      }
    } catch (e) { errors.push("内置OCR：" + (e && e.message || e)); }
  } else {
    errors.push("内置OCR：不可用（onnxruntime-node 未安装）");
  }

  const cli = loadCliTools();
  if (cli) {
    try {
      const r = await cli.ocrImage(imgPath);
      if (r.ok && r.text && r.text.trim()) {
        return { ok: true, text: r.text.trim(), engine: r.tool || "CLI-OCR", ms: r.ms };
      }
      errors.push("CLI OCR" + (r.tool ? "（" + r.tool + "）" : "") + "：" + (r.error || "无识别结果"));
    } catch (e) { errors.push("CLI OCR：" + (e && e.message || e)); }
  }

  return { ok: false, errors };
}

// ---------- 提取文字：本地 OCR 优先（纯文本版默认链路），vision provider 兜底 ----------
async function extractText(imgPath) {
  const t0 = Date.now();
  const local = await extractTextLocal(imgPath);
  if (local.ok) return local;

  const prompt = "请提取这张图片中的所有文字，原样逐行输出，不要添加任何解释或额外修饰。";
  const errors = ["本地 OCR 失败：" + local.errors.join("；")];
  try {
    const providers = availableProviders(loadConfig());
    if (providers.length) {
      const dataUrl = makeDataUrl(imgPath);
      for (const p of providers) {
        const r = await callProvider(p, dataUrl, prompt);
        if (r.ok && r.text && r.text.trim()) {
          return { ok: true, text: r.text.trim(), engine: p.name + "（视觉）", ms: Date.now() - t0 };
        }
        errors.push(p.name + "：" + r.error);
      }
      errors.push("视觉 provider 均失败");
    } else {
      errors.push("未配置视觉 provider");
    }
  } catch (e) { errors.push(e && e.message || e); }

  return { ok: false, error: errors.join("；") };
}

// ---------- 完整视觉分析：本地 OCR 优先（纯文本模型也能"看图读字"） ----------
// 先本地 OCR 提取文字；本地失败 / 需理解类分析时回退 vision provider（若已配置）
async function analyzeImage(imgPath, prompt) {
  const p = (prompt || "").trim() || "请描述这张图片的内容，并提取其中所有文字信息。";
  const t0 = Date.now();
  try {
    // 本地 OCR 优先（纯文本版默认链路）：直接提取图中文字
    const local = await extractTextLocal(imgPath);
    if (local.ok) {
      return { ok: true, text: local.text, engine: local.engine, ms: local.ms, note: "本地 OCR 提取（纯文本版默认链路）" };
    }
    // 兜底：vision provider（仅已配置视觉 key 时可用）
    const providers = availableProviders(loadConfig());
    if (providers.length) {
      const dataUrl = makeDataUrl(imgPath);
      const errors = [];
      for (const pr of providers) {
        const r = await callProvider(pr, dataUrl, p);
        if (r.ok) return { ok: true, text: r.text, engine: pr.name, ms: Date.now() - t0 };
        errors.push(pr.name + "：" + r.error);
      }
      return { ok: false, error: "本地 OCR 失败：" + local.errors.join("；") + "；视觉 provider 也失败：" + errors.join("；") };
    }
    return { ok: false, error: "本地 OCR 失败：" + local.errors.join("；") + "；且未配置视觉 provider 兜底" };
  } catch (e) {
    return { ok: false, error: (e && e.message) || String(e) };
  }
}

// 供 server.js / 其他模块调用
module.exports = { analyzeImage, extractText, extractTextLocal, callProvider, availableProviders, loadConfig, makeDataUrl };

// ---------- CLI 入口（仅直接运行时执行；被 require 时不触发，防 process.exit 误杀宿主进程） ----------
if (require.main === module) {
(async () => {
  const arg = process.argv[2];
  if (arg === "--dryrun") {
    try {
      const providers = availableProviders(loadConfig());
      console.log("[dryrun] config OK");
      providers.forEach(p => {
        console.log("[dryrun]   provider = " + p.name + " | model = " + p.model + " | apiKey set = true");
      });
      const total = loadConfig().length;
      console.log("[dryrun] 可用 provider " + providers.length + "/" + total + "（顺序即 fallback 链）");
      const img = process.argv[3];
      if (img && fs.existsSync(img)) console.log("[dryrun] image found:", img);
      else if (img) console.log("[dryrun] image NOT found:", img);
      const ocrJs = loadOcrJs();
      if (ocrJs) {
        const s = ocrJs.checkEngine();
        console.log("[dryrun] 内置 OCR 引擎: " + (s.ok ? "就绪" : "模型缺失") + "（det " + s.det + " / rec " + s.rec + " / dict " + s.dict + "）");
      } else {
        console.log("[dryrun] 内置 OCR 引擎: 不可用（onnxruntime-node 未安装）");
      }
      console.log("[dryrun] script syntax & config load OK");
      process.exit(0);
    } catch (e) {
      console.error("[dryrun] FAILED:", e.message);
      process.exit(1);
    }
  }

  const imgPath = arg;
  const promptArg = process.argv[3];
  if (!imgPath) {
    console.error('Usage: node vision_analyze.js <imagePath> "[prompt]"');
    process.exit(1);
  }
  if (!fs.existsSync(imgPath)) {
    console.error("ERROR: image not found:", imgPath);
    process.exit(1);
  }
  const prompt = promptArg || "请描述这张图片的内容，并提取其中所有文字信息。";
  const r = await analyzeImage(imgPath, prompt);
  if (r.ok) {
    if (r.engine) console.error("[vision_analyze] 引擎: " + r.engine + (r.ms != null ? "（" + r.ms + "ms）" : ""));
    if (r.note) console.error("[vision_analyze] 备注: " + r.note);
    console.log(r.text); // stdout 只输出结果文本，日志走 stderr
    process.exit(0);
  }
  console.error("[vision_analyze] 失败: " + (r.error || "未知错误"));
  process.exit(1);
})().catch(e => { console.error("FATAL:", e && e.message ? e.message : e); process.exit(1); });
}
