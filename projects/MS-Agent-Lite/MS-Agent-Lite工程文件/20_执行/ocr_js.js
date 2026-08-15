// ocr_js.js — 纯 JS 本地 OCR 引擎（onnxruntime-node + PP-OCRv4 轻量模型）
// 定位：面试准备助手内置离线 OCR——开箱即用（模型打包进仓库 assets/ocr，无需 Python、无需额外下载），
//       为纯文本模型（如 DeepSeek）提供本地"看图读字"能力，解耦对多模态 provider 的依赖。
// 依赖：onnxruntime-node（npm，含 Windows 预编译二进制）、@napi-rs/canvas（项目既有，图像解码/渲染）。
// 用法：
//   node ocr_js.js <image>      # OCR 识别图片文字
//   node ocr_js.js --selftest   # 自测：canvas 生成中文测试图并识别，验证引擎可用
//   node ocr_js.js --info       # 打印引擎与模型状态
const ort = require("onnxruntime-node");
const fs = require("fs");
const path = require("path");
const { loadImage, createCanvas } = require("@napi-rs/canvas");

const ASSETS = path.join(__dirname, "assets", "ocr");
const DET_PATH = path.join(ASSETS, "ch_PP-OCRv4_det_infer.onnx");
const REC_PATH = path.join(ASSETS, "ch_PP-OCRv4_rec_infer.onnx");
const DICT_PATH = path.join(ASSETS, "ppocr_keys_v1.txt");

// ---- 参数（与 PaddleOCR / RapidOCR 默认一致） ----
const DET_LIMIT_SIDE = 960;    // det 最长边上限
const DET_THRESH = 0.3;        // DB 概率图二值化阈值
const UNCLIP_RATIO = 1.5;      // 文本框扩张系数（与 PaddleOCR 默认一致；过小会裁掉字符边缘，如 °/笔画）
const MIN_BOX_AREA = 9;        // 连通域最小面积（约 3x3）
const DET_MEAN = [0.485, 0.456, 0.406];
const DET_STD = [0.229, 0.224, 0.225];
const REC_H = 48;
const REC_MAX_W = 320;         // rec 宽度上限（与训练一致）
const REC_MEAN = [0.5, 0.5, 0.5];
const REC_STD = [0.5, 0.5, 0.5];

let _sessions = null;   // {det, rec}
let _keys = null;       // 字符表（index 0 = blank，字符从 1 开始）

// 惰性加载模型与字符表（server 常驻时只在首次调用时创建 session）
async function ensureSessions() {
  if (_sessions) return _sessions;
  if (!fs.existsSync(DET_PATH) || !fs.existsSync(REC_PATH) || !fs.existsSync(DICT_PATH)) {
    const e = new Error("OCR 模型文件缺失（assets/ocr/ 下应有 ch_PP-OCRv4_det_infer.onnx / ch_PP-OCRv4_rec_infer.onnx / ppocr_keys_v1.txt）");
    e.code = "MODEL_MISSING";
    throw e;
  }
  const [det, rec] = await Promise.all([
    ort.InferenceSession.create(DET_PATH),
    ort.InferenceSession.create(REC_PATH)
  ]);
  _sessions = { det, rec };
  // 字符表构建严格复刻 PaddleOCR：逐行拼接（只去行尾 \r\n），末尾追加空格（use_space_char）
  // 注意：for...of 按 code point 迭代，可正确处理扩展区汉字（surrogate pair）
  // 字典 6623 个字符（UTF-16 长度 6624，含 1 个代理对字符）+ space = 6624 → blank + 6624 = C=6625
  let charStr = "";
  for (const ln of fs.readFileSync(DICT_PATH, "utf8").split("\n")) {
    let s = ln;
    if (s.endsWith("\r")) s = s.slice(0, -1);
    charStr += s;
  }
  charStr += " "; // use_space_char：末尾空格
  _keys = [""];   // index 0 = blank
  for (const ch of charStr) _keys.push(ch);
  return _sessions;
}

// 引擎可用性检查（供 UI/接入方快速判断，不抛异常）
function checkEngine() {
  return {
    ok: fs.existsSync(DET_PATH) && fs.existsSync(REC_PATH) && fs.existsSync(DICT_PATH),
    det: fs.existsSync(DET_PATH) ? Math.round(fs.statSync(DET_PATH).size / 1024) + "KB" : "缺失",
    rec: fs.existsSync(REC_PATH) ? Math.round(fs.statSync(REC_PATH).size / 1024) + "KB" : "缺失",
    dict: fs.existsSync(DICT_PATH) ? "OK" : "缺失"
  };
}

// ---------- 图像解码 → {w, h, rgba} ----------
async function decodeImage(imgPath) {
  const img = await loadImage(imgPath);
  const canvas = createCanvas(img.width, img.height);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, img.width, img.height).data; // RGBA
  return { w: img.width, h: img.height, rgba: data };
}

// ---------- 双线性缩放（RGB Float32Array） ----------
function resizeRGB(src, sw, sh, dw, dh) {
  const out = new Float32Array(dw * dh * 3);
  const xr = sw / dw, yr = sh / dh;
  for (let y = 0; y < dh; y++) {
    const sy = y * yr;
    const y0 = Math.floor(sy), y1 = Math.min(y0 + 1, sh - 1);
    const fy = sy - y0;
    for (let x = 0; x < dw; x++) {
      const sx = x * xr;
      const x0 = Math.floor(sx), x1 = Math.min(x0 + 1, sw - 1);
      const fx = sx - x0;
      const i00 = (y0 * sw + x0) * 4, i10 = (y0 * sw + x1) * 4;
      const i01 = (y1 * sw + x0) * 4, i11 = (y1 * sw + x1) * 4;
      const o = (y * dw + x) * 3;
      for (let c = 0; c < 3; c++) {
        const top = src[i00 + c] * (1 - fx) + src[i10 + c] * fx;
        const bot = src[i01 + c] * (1 - fx) + src[i11 + c] * fx;
        out[o + c] = top * (1 - fy) + bot * fy;
      }
    }
  }
  return out;
}

// ---------- det 预处理 → {tensor, detW, detH, scaleX, scaleY} ----------
function detPreprocess(rgba, w, h) {
  const ratio = Math.min(DET_LIMIT_SIDE / Math.max(h, w), 1.0);
  let dh = Math.max(Math.round((h * ratio) / 32) * 32, 32);
  let dw = Math.max(Math.round((w * ratio) / 32) * 32, 32);
  // 归一化后的 RGB CHW，均值/方差与 PaddleOCR DetNormalize 一致
  const rgb = resizeRGB(rgba, w, h, dw, dh);
  const n = dw * dh;
  const chw = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < 3; c++) {
      chw[c * n + i] = (rgb[i * 3 + c] / 255 - DET_MEAN[c]) / DET_STD[c];
    }
  }
  return {
    tensor: new ort.Tensor("float32", chw, [1, 3, dh, dw]),
    detW: dw, detH: dh,
    scaleX: w / dw, scaleY: h / dh
  };
}

// ---------- 概率图 → 连通域 → 文本框（AABB + unclip） ----------
// prob: Float32Array 长度 W*H（det 输出）
function boxesFromProb(prob, W, H, scaleX, scaleY) {
  const visited = new Uint8Array(W * H);
  const boxes = [];
  const queue = new Int32Array(W * H);
  const N = W * H;
  for (let start = 0; start < N; start++) {
    if (visited[start] || prob[start] <= DET_THRESH) continue;
    // BFS 收集 4-连通区域
    let head = 0, tail = 0;
    queue[tail++] = start;
    visited[start] = 1;
    let minX = W, maxX = -1, minY = H, maxY = -1, area = 0, sumP = 0;
    while (head < tail) {
      const p = queue[head++];
      const x = p % W, y = (p / W) | 0;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      area++; sumP += prob[p];
      const nb = [];
      if (x > 0) nb.push(p - 1);
      if (x < W - 1) nb.push(p + 1);
      if (y > 0) nb.push(p - W);
      if (y < H - 1) nb.push(p + W);
      for (const q of nb) {
        if (!visited[q] && prob[q] > DET_THRESH) { visited[q] = 1; queue[tail++] = q; }
      }
    }
    if (area < MIN_BOX_AREA) continue;
    // unclip：沿 AABB 四边外扩（offset = area * ratio / perimeter）
    const bw = maxX - minX + 1, bh = maxY - minY + 1;
    const offset = (area * UNCLIP_RATIO) / (2 * (bw + bh));
    const x1 = Math.max(Math.floor(minX - offset), 0);
    const y1 = Math.max(Math.floor(minY - offset), 0);
    const x2 = Math.min(Math.ceil(maxX + offset), W - 1);
    const y2 = Math.min(Math.ceil(maxY + offset), H - 1);
    const score = sumP / area;
    // 映射回原图坐标
    boxes.push({
      x1: x1 * scaleX, y1: y1 * scaleY,
      x2: (x2 + 1) * scaleX, y2: (y2 + 1) * scaleY,
      score, area: bw * bh
    });
  }
  // 按中心 y 排序（阅读顺序，从上到下）
  boxes.sort((a, b) => (a.y1 + a.y2) / 2 - (b.y1 + b.y2) / 2);
  return boxes;
}

// ---------- rec：裁剪 + 预处理 + 推理 + CTC 解码 ----------
async function recognizeRegion(rgba, w, h, crop) {
  const x1 = Math.max(Math.floor(crop.x1), 0), y1 = Math.max(Math.floor(crop.y1), 0);
  const x2 = Math.min(Math.ceil(crop.x2), w), y2 = Math.min(Math.ceil(crop.y2), h);
  const cw = Math.max(x2 - x1, 1), ch = Math.max(y2 - y1, 1);
  // 从 RGBA 里取裁剪区域的 RGBA（resizeRGB 按 4 通道读取，与 det 链路一致）
  const sub = new Float32Array(cw * ch * 4);
  for (let yy = 0; yy < ch; yy++) {
    const srcOff = ((y1 + yy) * w + x1) * 4;
    const dstOff = yy * cw * 4;
    for (let xx = 0; xx < cw; xx++) {
      sub[dstOff + xx * 4] = rgba[srcOff + xx * 4];
      sub[dstOff + xx * 4 + 1] = rgba[srcOff + xx * 4 + 1];
      sub[dstOff + xx * 4 + 2] = rgba[srcOff + xx * 4 + 2];
      sub[dstOff + xx * 4 + 3] = 255;
    }
  }
  // 等比例缩放：高固定 48，宽按比例（等比，避免压扁文字；超长行设性能上限 1024）
  let rw = Math.ceil((REC_H * cw) / ch);
  rw = Math.max(rw, 16);
  if (rw > 1024) rw = 1024;
  const scaled = resizeRGB(sub, cw, ch, rw, REC_H);
  // 归一化 RecNormalize：/255 - 0.5 / 0.5
  const n = rw * REC_H;
  const chw = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < 3; c++) {
      chw[c * n + i] = (scaled[i * 3 + c] / 255 - REC_MEAN[c]) / REC_STD[c];
    }
  }
  const sess = _sessions;
  const out = await sess.rec.run({ x: new ort.Tensor("float32", chw, [1, 3, REC_H, rw]) });
  const key = Object.keys(out)[0]; // softmax_11.tmp_0
  const logits = out[key].data;    // Float32Array, dims [1, T, C]
  const dims = out[key].dims;
  const T = dims[1], C = dims[2];
  // CTC 贪心解码：每列 argmax → 去重 → 去 blank → 映射字符
  const idx = new Array(T);
  for (let t = 0; t < T; t++) {
    let best = 0, bv = -Infinity;
    for (let c = 0; c < C; c++) {
      const v = logits[t * C + c];
      if (v > bv) { bv = v; best = c; }
    }
    idx[t] = best;
  }
  let text = "";
  for (let t = 0; t < T; t++) {
    if (idx[t] === 0) continue;              // blank
    if (t > 0 && idx[t] === idx[t - 1]) continue; // 相邻重复
    text += _keys[idx[t]] || "";
  }
  return text;
}

// ---------- 主入口 ----------
async function ocrImage(imgPath) {
  const t0 = Date.now();
  await ensureSessions();
  const { w, h, rgba } = await decodeImage(imgPath);
  const det = detPreprocess(rgba, w, h);
  const out = await _sessions.det.run({ x: det.tensor });
  const key = Object.keys(out)[0]; // sigmoid_0.tmp_0
  const prob = out[key].data;      // Float32Array
  const boxes = boxesFromProb(prob, det.detW, det.detH, det.scaleX, det.scaleY);
  const lines = [];
  for (const b of boxes) {
    const text = await recognizeRegion(rgba, w, h, b);
    const t = text.trim(); // 去掉检测框 unclip 引入的首尾空白
    if (t) lines.push({ text: t, box: [b.x1, b.y1, b.x2, b.y2], score: b.score });
  }
  return {
    ok: true,
    text: lines.map(l => l.text).join("\n"),
    lines,
    imgW: w, imgH: h,
    ms: Date.now() - t0
  };
}

// ---------- 自测：canvas 生成中文测试图并识别 ----------
async function selfTest() {
  const tmp = path.join(require("os").tmpdir(), "msa-ocr-selftest-" + Date.now() + ".png");
  const canvas = createCanvas(760, 220);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, 760, 220);
  ctx.fillStyle = "#000";
  ctx.font = "34px Microsoft YaHei, SimHei, sans-serif";
  ctx.fillText("面试准备助手 本地 OCR 引擎自测", 24, 70);
  ctx.fillText("Resume PDF OCR 2026-08-06", 24, 140);
  ctx.fillText("中文识别 quality 测试 line3", 24, 200);
  fs.writeFileSync(tmp, canvas.toBuffer("image/png"));
  const r = await ocrImage(tmp);
  try { fs.unlinkSync(tmp); } catch (e) {}
  return r;
}

// ---------- CLI 自测入口（仅直接运行时执行，被 require 不触发） ----------
if (require.main === module) {
(async () => {
  const arg = process.argv[2];
  if (arg === "--info" || !arg) {
    const s = checkEngine();
    console.log("OCR 引擎状态: " + (s.ok ? "就绪" : "模型缺失"));
    console.log("  det: " + s.det + "  rec: " + s.rec + "  dict: " + s.dict);
    console.log("  推理后端: onnxruntime-node " + require("onnxruntime-node/package.json").version);
    process.exit(0);
  }
  if (arg === "--selftest") {
    console.log("生成中文测试图并识别…");
    const r = await selfTest();
    console.log("耗时 " + r.ms + "ms，检测到 " + r.lines.length + " 行：");
    for (const l of r.lines) console.log("  [" + l.text + "]");
    console.log("---");
    console.log(r.text);
    process.exit(0);
  }
  if (arg === "--ocr" || (arg && !arg.startsWith("-"))) {
    const f = process.argv[3] || arg;
    const r = await ocrImage(f);
    console.log("[ocr_js] 耗时=" + r.ms + "ms 行数=" + r.lines.length + " 尺寸=" + r.imgW + "x" + r.imgH);
    console.log(r.text);
    process.exit(0);
  }
  console.error("未知参数: " + arg + "（支持 <image> / --selftest / --info）");
  process.exit(1);
})().catch(e => { console.error("FATAL:", e.message); process.exit(1); });
}

module.exports = { ocrImage, checkEngine };
