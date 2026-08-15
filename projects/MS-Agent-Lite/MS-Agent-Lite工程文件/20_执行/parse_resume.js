// parse_resume.js — 简历文本解析（本地插件，小任务）
// 支持格式：.pdf（pdfjs-dist，动态 import）/ .docx（mammoth）/ .txt / .md
// 入口：parseResumeFromBuffer(buffer, ext) / parseResumeFromFile(filePath)
const fs = require("fs");
const path = require("path");

function stripBom(s) {
  return s.charCodeAt(0) === 0xFEFF ? s.slice(1) : s;
}

// PDF：与 pdf_extract.js 同机制（动态 import pdfjs-dist v6，worker 转 file:// URL）
async function parsePdf(buffer) {
  const pdfjsLib = await import("pdfjs-dist/legacy/build/pdf.mjs");
  try {
    const workerFile = path.join(
      path.dirname(require.resolve("pdfjs-dist/package.json")),
      "legacy", "build", "pdf.worker.mjs"
    );
    pdfjsLib.GlobalWorkerOptions.workerSrc = require("url").pathToFileURL(workerFile).href;
  } catch (e) { /* non-fatal */ }

  const doc = await pdfjsLib.getDocument({ data: new Uint8Array(buffer), useWorkerFetch: false, isEvalSupported: false }).promise;
  const pages = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    // 按 y 跳变断行，还原行结构
    let prevY = null;
    const lines = [];
    let cur = "";
    for (const it of content.items) {
      const t = it.str !== undefined ? it.str : "";
      if (prevY !== null && it.transform && Math.abs(it.transform[5] - prevY) > 3) {
        if (cur.trim()) lines.push(cur.trim());
        cur = "";
      }
      cur += t;
      if (it.transform) prevY = it.transform[5];
    }
    if (cur.trim()) lines.push(cur.trim());
    pages.push(lines.join("\n"));
  }
  return pages.join("\n\n");
}

// DOCX：mammoth extractRawText（文档中文字/表格均提取为纯文本）
async function parseDocx(buffer) {
  const mammoth = require("mammoth");
  const r = await mammoth.extractRawText({ buffer });
  return (r.value || "").trim();
}

// TXT / MD：优先 UTF-8；检测 BOM 判定 UTF-16/UTF-32；UTF-8 解码含替换符时回退 GBK
// （中文用户"Word 另存为 txt"常产出 GBK/ANSI，记事本"Unicode"是 UTF-16——P1-2 防乱码简历静默进入生成）
function parseText(buffer) {
  const b = buffer;
  // UTF-16/UTF-32 BOM 判定
  if (b.length >= 2 && b[0] === 0xFF && b[1] === 0xFE) {
    if (b.length >= 4 && b[2] === 0x00 && b[3] === 0x00) return b.toString("utf8").trim(); // UTF-32LE（罕见，兜底）
    return stripBom(b.toString("utf16le")).trim();
  }
  if (b.length >= 2 && b[0] === 0xFE && b[1] === 0xFF) {
    // UTF-16BE：交换字节序后用 LE 解码
    const swapped = Buffer.alloc(b.length - 2);
    for (let i = 2; i < b.length; i += 2) { swapped[i - 2] = b[i + 1]; swapped[i - 1] = b[i]; }
    return swapped.toString("utf16le").trim();
  }
  // 默认按 UTF-8
  let s = stripBom(b.toString("utf8"));
  // 出现替换符 U+FFFD → UTF-8 解码失败，尝试 GBK（Windows 中文默认 ANSI 编码）
  if (s.indexOf("\uFFFD") >= 0) {
    try {
      const gbk = new TextDecoder("gbk").decode(b);
      if (gbk.indexOf("\uFFFD") < 0) return stripBom(gbk).trim();
    } catch (e) { /* 当前运行时无 gbk 支持则保持原结果 */ }
  }
  return s.trim();
}

// parseResumeFromBuffer(buffer, ext) → { text, meta: {ext, size, lines} }
async function parseResumeFromBuffer(buffer, ext) {
  if (!Buffer.isBuffer(buffer)) buffer = Buffer.from(buffer);
  ext = (ext || "").toLowerCase().replace(/^\./, "");
  let text;
  if (ext === "pdf") text = await parsePdf(buffer);
  else if (ext === "docx") text = await parseDocx(buffer);
  else if (ext === "txt" || ext === "md" || ext === "text") text = parseText(buffer);
  else if (ext === "doc") throw new Error("暂不支持旧版 .doc：请用 Word 打开后「另存为」.docx 或 .txt 再上传（约 1 分钟）");
  else throw new Error("不支持的格式: " + ext + "（支持 pdf / docx / txt / md）");
  const meta = { ext, size: buffer.length, lines: text.split("\n").length };
  // 空文件/无可提取文字：明确报错，避免"以空简历生成"的静默失败（P2-5）
  if (!text.trim()) throw new Error("文件内容为空或无法提取文字（" + ext + "）——请确认简历内容后重新上传");
  // 扫描件检测：图片型/扫描型 PDF 解析出的文字极少，标记后由前端提示用户换文字版，避免"无简历依据"的静默失败
  if (ext === "pdf" && text.trim().length < 200) meta.suspectedScan = true;
  return { text, meta };
}

// parseResumeFromFile(filePath) → { text, meta }
async function parseResumeFromFile(filePath) {
  const ext = path.extname(filePath).slice(1);
  const buffer = fs.readFileSync(filePath);
  return parseResumeFromBuffer(buffer, ext);
}

module.exports = { parseResumeFromBuffer, parseResumeFromFile };
