// cli_tools.js — 本地 CLI 工具适配层（P0：探测 + 统一调用）
// 定位：让面试准备助手可选地利用本地 CLI（markitdown / mineru / rapidocr 等）：
//   1. PDF/DOCX → 结构化 Markdown（替代 pdfjs/mammoth 的纯文本抽取，降 token）
//   2. 图片 → 文字（本地 OCR，解耦"视觉依赖多模态 provider"）
// 原则：CLI 全部为"可选增强"——工具缺失时调用方回退原实现，绝不阻塞主流程。
// 用法：
//   node cli_tools.js --probe            # 探测 PATH 上可用的 CLI 工具
//   node cli_tools.js --pdf <file>       # 文档 → Markdown（markitdown 优先，mineru 兜底）
//   node cli_tools.js --ocr <image>      # 图片 → 文字（rapidocr 优先，paddleocr/markitdown 兜底）
const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");

const IS_WIN = process.platform === "win32";

// 可选覆盖：config.json 里可写 {"cli":{"pdf":"markitdown","ocr":"rapidocr"}}
// 缺失/为空 = 按探测顺序自动选择；非法值自动忽略
let CLI_CFG = {};
try {
  const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf8"));
  if (cfg && typeof cfg.cli === "object") CLI_CFG = cfg.cli || {};
} catch (e) { /* config 缺失/损坏：走自动选择 */ }

// 工具清单：bin 为可执行名，alt 为备选可执行名（探测到其一即算安装）
const TOOLS = [
  { id: "markitdown", role: "pdf", bin: "markitdown", alt: [], desc: "微软 MarkItDown：PDF/DOCX/XLSX → Markdown（MIT，轻量，默认首选）", install: "pip install 'markitdown[pdf,docx,xlsx]'" },
  { id: "mineru",     role: "pdf", bin: "mineru",     alt: [], desc: "上海AI实验室 MinerU：高保真解析（版面/扫描件OCR/公式/表格，AGPL，可选增强）", install: "pip install -U \"mineru[all]\"" },
  { id: "rapidocr",   role: "ocr", bin: "rapidocr_onnxruntime", alt: ["rapidocr"], desc: "RapidOCR：轻量离线 OCR（ONNX，中文准，低配可跑）", install: "pip install rapidocr_onnxruntime" },
  { id: "paddleocr",  role: "ocr", bin: "paddleocr",  alt: [], desc: "PaddleOCR：精度高但依赖重（备选）", install: "pip install paddleocr" }
];

function probeBin(bin) {
  return new Promise((resolve) => {
    const cmd = IS_WIN ? "where" : "which";
    execFile(cmd, [bin], { timeout: 5000 }, (err, stdout) => {
      if (!err && stdout && stdout.trim()) {
        resolve(stdout.trim().split(/\r?\n/)[0]);
      } else {
        resolve(null);
      }
    });
  });
}

// 探测所有工具：返回 [{id, role, found, binPath, desc, install}]
async function probeAll() {
  const out = [];
  for (const t of TOOLS) {
    let binPath = await probeBin(t.bin);
    if (!binPath) {
      for (const a of t.alt) { binPath = await probeBin(a); if (binPath) break; }
    }
    out.push({ id: t.id, role: t.role, bin: t.bin, found: !!binPath, binPath: binPath || null, desc: t.desc, install: t.install });
  }
  return out;
}

// 统一子进程调用（复用 pipeline runChild 的超时模式，P0 默认 120s）
function runCli(bin, args, timeoutMs) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const child = execFile(bin, args, { encoding: "utf8", maxBuffer: 32 * 1024 * 1024, timeout: timeoutMs || 120000 }, (err, stdout, stderr) => {
      if (err) {
        // 超时或执行失败：把可读信息带出去
        const detail = (stderr && stderr.trim()) || (stdout && stdout.trim()) || (err && err.message) || String(err);
        resolve({ ok: false, error: detail, stdout: stdout || "", ms: Date.now() - t0 });
      } else {
        resolve({ ok: true, stdout: stdout || "", stderr: stderr || "", ms: Date.now() - t0 });
      }
    });
    child.on("error", () => { /* execFile 回调已处理 */ });
  });
}

// 选取指定角色（pdf/ocr）的优先工具：显式配置 > 探测顺序
async function pickTool(role) {
  const probes = await probeAll();
  const configured = CLI_CFG[role];
  if (configured) {
    const hit = probes.find(t => t.id === configured && t.found);
    if (hit) return hit;
  }
  return probes.find(t => t.role === role && t.found) || null;
}

function tempOut(ext) {
  const p = path.join(require("os").tmpdir(), "msa-cli-" + Date.now() + "-" + Math.floor(Math.random() * 1e6) + ext);
  return p;
}

// ---------- 文档 → Markdown（markitdown 优先，mineru 兜底） ----------
async function convertToMarkdown(filePath) {
  const tool = await pickTool("pdf");
  if (!tool) return { ok: false, error: "未检测到本地文档转换 CLI（markitdown/mineru）。安装命令见 --probe 输出；未安装时请走原解析流程。" };
  const abs = path.resolve(filePath);
  if (!fs.existsSync(abs)) return { ok: false, error: "文件不存在: " + abs };

  if (tool.id === "markitdown") {
    const outMd = tempOut(".md");
    const r = await runCli(tool.binPath, [abs, "-o", outMd]);
    if (!r.ok) { try { fs.unlinkSync(outMd); } catch (e) {} return { ok: false, error: "markitdown 失败: " + r.error, tool: "markitdown" }; }
    const md = fs.readFileSync(outMd, "utf8");
    try { fs.unlinkSync(outMd); } catch (e) {}
    return { ok: true, text: md, tool: "markitdown", ms: r.ms };
  }

  if (tool.id === "mineru") {
    const outDir = tempOut("");
    fs.mkdirSync(outDir, { recursive: true });
    const r = await runCli(tool.binPath, ["-p", abs, "-o", outDir, "--task", "doc"]);
    if (!r.ok) { try { fs.rmSync(outDir, { recursive: true, force: true }); } catch (e) {} return { ok: false, error: "mineru 失败: " + r.error, tool: "mineru" }; }
    // mineru 输出目录结构不固定，递归找 .md 后合并
    const mds = [];
    (function walk(d) {
      for (const f of fs.readdirSync(d)) {
        const fp = path.join(d, f);
        if (fs.statSync(fp).isDirectory()) walk(fp);
        else if (/\.md$/i.test(f)) mds.push(fp);
      }
    })(outDir);
    let md = "";
    for (const f of mds.sort()) md += fs.readFileSync(f, "utf8") + "\n\n";
    try { fs.rmSync(outDir, { recursive: true, force: true }); } catch (e) {}
    if (!md.trim()) return { ok: false, error: "mineru 未产出 Markdown", tool: "mineru" };
    return { ok: true, text: md, tool: "mineru", ms: r.ms };
  }

  return { ok: false, error: "不支持的工具: " + tool.id };
}

// ---------- 图片 → 文字（rapidocr 优先，paddleocr/markitdown 兜底） ----------
async function ocrImage(imgPath) {
  const tools = (await probeAll()).filter(t => t.role === "ocr" && t.found);
  const pick = CLI_CFG.ocr ? tools.find(t => t.id === CLI_CFG.ocr) : (tools.find(t => t.id === "rapidocr") || tools[0]);
  if (!pick) return { ok: false, error: "未检测到本地 OCR CLI（rapidocr/paddleocr）。安装命令见 --probe 输出；未安装时请走原视觉 provider 流程。" };
  const abs = path.resolve(imgPath);
  if (!fs.existsSync(abs)) return { ok: false, error: "图片不存在: " + abs };

  if (pick.id === "rapidocr") {
    // rapidocr_onnxruntime CLI：-img 输入，-out 结果文件（可选）；stdout 也会输出识别文本
    const r = await runCli(pick.binPath, ["-img", abs]);
    if (!r.ok) return { ok: false, error: "rapidocr 失败: " + r.error, tool: "rapidocr" };
    // 提取识别文本行：rapidocr CLI 输出形如 "文本内容,置信度"，直接取全部 stdout 作为文本
    const text = (r.stdout || "").trim();
    if (!text) return { ok: false, error: "rapidocr 无识别结果", tool: "rapidocr" };
    return { ok: true, text, tool: "rapidocr", ms: r.ms };
  }

  if (pick.id === "paddleocr") {
    const r = await runCli(pick.binPath, ["--image_dir", abs, "--lang", "ch"]);
    if (!r.ok) return { ok: false, error: "paddleocr 失败: " + r.error, tool: "paddleocr" };
    const text = (r.stdout || "").trim();
    if (!text) return { ok: false, error: "paddleocr 无识别结果", tool: "paddleocr" };
    return { ok: true, text, tool: "paddleocr", ms: r.ms };
  }

  return { ok: false, error: "不支持的工具: " + pick.id };
}

// ---------- CLI 自测入口（仅当直接运行本文件时执行，被 require 时不触发） ----------
if (require.main === module) {
(async () => {
  const arg = process.argv[2];
  if (arg === "--probe" || !arg) {
    const list = await probeAll();
    console.log("本地 CLI 工具探测结果（P0 适配层）:");
    for (const t of list) {
      console.log((t.found ? "  [已安装] " : "  [未安装] ") + t.id.padEnd(12) + t.desc);
      if (t.found) console.log("          路径: " + t.binPath);
      else console.log("          安装: " + t.install);
    }
    const pdf = list.find(t => t.role === "pdf" && t.found);
    const ocr = list.find(t => t.role === "ocr" && t.found);
    console.log("---");
    console.log("PDF 角色当前可用: " + (pdf ? pdf.id : "无（回退 pdfjs/mammoth）"));
    console.log("OCR 角色当前可用: " + (ocr ? ocr.id : "无（回退 vision provider）"));
    process.exit(0);
  }
  if (arg === "--pdf") {
    const f = process.argv[3];
    if (!f) { console.error("用法: node cli_tools.js --pdf <file>"); process.exit(1); }
    const r = await convertToMarkdown(f);
    if (!r.ok) { console.error("ERROR:", r.error); process.exit(1); }
    console.log("[cli_tools] 工具=" + r.tool + " 耗时=" + r.ms + "ms 长度=" + r.text.length);
    console.log(r.text);
    process.exit(0);
  }
  if (arg === "--ocr") {
    const f = process.argv[3];
    if (!f) { console.error("用法: node cli_tools.js --ocr <image>"); process.exit(1); }
    const r = await ocrImage(f);
    if (!r.ok) { console.error("ERROR:", r.error); process.exit(1); }
    console.log("[cli_tools] 工具=" + r.tool + " 耗时=" + r.ms + "ms");
    console.log(r.text);
    process.exit(0);
  }
  console.error("未知参数: " + arg + "（支持 --probe / --pdf <file> / --ocr <image>）");
  process.exit(1);
})().catch(e => { console.error("FATAL:", e && e.message ? e.message : e); process.exit(1); });
}

// 导出供 server.js 等模块使用
module.exports = { probeAll, convertToMarkdown, ocrImage, runCli };
