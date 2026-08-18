// quality_check.js — M3 规则可查项（SOP-07）
// 零 token 成本先行：正则 / 集合 diff / 上下文指纹判定，critical 命中直接回炉（LLM 无权推翻红线）。
// 检查项：
//   D1 数字口径（基准 = 参与边界卡 + 上传简历；上下文指纹不一致 / 指标形态越界 → critical，基准外裸数字 → warn）
//   D2 项目真实性（另一版本专属项目在材料中作为【项目】出现 → warn；基准外编造项目 → critical）
//   D4 结构完整性（截断 / 一级标题 / 代码围栏破坏 → critical；组件框架缺失 → warn）
//   D5 术语一致性（大小写混用 → warn）
const fs = require("fs");
const path = require("path");
const { GLOSSARY } = require("./glossary.js");
const components = require("./components/index.js");

// ---------- 通用 ----------
function normalizeCtx(raw) {
  // 数字归一为 <N>，保留 % 后缀（isMetricShape 依赖 <N>% 识别指标形态），空白压缩
  return String(raw || "")
    .replace(/\d+(?:\.\d+)?\s*%/g, "<N>%")
    .replace(/\d+(?:\.\d+)?/g, "<N>")
    .replace(/\s+/g, " ").trim();
}

// 提取候选数字（含多轮抽检调优：过滤非简历指标数字——流程时长/小节号/匹配度自评/模型规模/日期/参数赋值等）
function extractNumbers(text) {
  const nums = [];
  const re = /\d+(?:\.\d+)?\s*%?/g;
  let m;
  while ((m = re.exec(String(text || "")))) {
    const raw = m[0];
    const i = m.index;
    // 上下文窗口按行截断：指标上下文通常在同一句内，跨行内容（章节标题等）会干扰篡改指纹匹配（M3 抽检调优）
    const before = String(text).slice(Math.max(0, i - 12), i).split("\n").pop();
    const after = String(text).slice(i + raw.length, i + raw.length + 12).split("\n")[0];
    const num = raw.replace(/\s*%$/, "%").trim();
    // 过滤：年份（19xx/20xx 四位）
    if (/^(?:19|20)\d{2}$/.test(num)) continue;
    // 过滤：行首序号 / 小节号 / 日期
    const lineStart = String(text).lastIndexOf("\n", i - 1) + 1;
    const prefix = String(text).slice(lineStart, i);
    if (/^\s*$/.test(prefix)) continue;
    if (/^\d+[\.、．)]$/.test(prefix.trim())) continue;
    if (/^[（(]\d+[）)]?$/.test(prefix.trim())) continue;
    if (/^\d+[./-]$/.test(prefix.trim())) continue;
    if (/^\.$/.test(before.trim())) continue;
    if (/http|www|\.com|\.cn|localhost|:\d{2,}/i.test(before + after)) continue;
    if (/\d{10,}/.test(num)) continue;
    // ---- 非简历指标数字不参与 D1（M3 规则抽检调优）----
    // 日期 token（"2026.09"）
    if (/^(?:19|20)\d{2}[./-]\d{1,2}(?:[./-]\d{1,2})?$/.test(num.trim())) continue;
    // 范围区间数字（"45-60"两端）
    const head2 = String(text).slice(Math.max(0, i - 2), i);
    if (/^\s*[-~–]\s*\d/.test(after) || /\d\s*[-~–]\s*$/.test(head2)) continue;
    // 标题小节号（"### 4.1"）
    if (/\d+\.\d+/.test(num) && /#{1,6}\s*$/.test(prefix.trim())) continue;
    // 表格单元格独占数字（"| 7 |"）
    if (/\|\s*$/.test(prefix.trim()) && /^\s*\|/.test(after.trim())) continue;
    // 文件名前缀序号（"02_项目深挖"）
    if (/^_\S/.test(after) && num.indexOf("%") < 0) continue;
    // 章节时长标记（"## 90秒完整版"）
    if (/^秒/.test(after.trim())) continue;
    // 举例/陷阱序号（"（如150/200）"、"陷阱7"）
    if (/[如例等][（(]?["“”'’]?\s*$/.test(prefix.trim())) continue;
    if (/陷阱\s*$/.test(prefix.trim())) continue;
    // 范围尾（"150/200" 中的 200）
    if (/\d\/\s*$/.test(prefix.trim())) continue;
    // 匹配度/契合度/相似度自评
    if (/匹配度|契合度|相似度/.test(before)) continue;
    // 切流/转移比例（"10%→50%→100%"）
    if (/^\s*[→⟶⇢>]/.test(after) || /[→⟶⇢>]\s*$/.test(prefix.trim()) || /%\s*[→⟶⇢>]/.test(after)) continue;
    // 时长/流程上下文
    if (/分钟|小时|min\b|天内?|个月/.test(after) || /分钟|小时|min\b|天内?|个月/.test(head2)) continue;
    // 模型规模后缀（"70B 模型" "500GB"）
    if (/^\s*[KMBG]+\b/.test(after)) continue;
    nums.push({ num, ctx: normalizeCtx(before + "<N>" + after) });
  }
  return nums;
}

// 指标形态判定：带 % 或 ×倍/单位/N+ 后缀才算「指标数字」（裸数字仅 warn）
function isMetricShape(ctx) {
  if (/<N>%/.test(ctx)) return true;
  return /<N>[%×x+倍]/.test(ctx) || /<N>(?:ms|s|GB|MB|KB|tok|tps|路|卡|万|亿|分钟?|小时|天内?|个月)/.test(ctx);
}

// ---------- D1 数字口径 ----------
// baseText：参与边界卡 + 上传简历（权威基准）；mdText：待审核材料
// 篡改判定：上下文指纹（数字归一）相同但数字不同 → critical（口径不符）
// 越界判定：基准集之外的指标形态数字 → critical；裸数字（≥2）→ warn
function checkDigitConsistency(baseText, mdText, file) {
  const issues = [];
  const baseNums = extractNumbers(baseText);
  const baseFp = new Map(); // ctx -> Set<num>
  const baseSet = new Set();
  for (const n of baseNums) {
    baseSet.add(n.num);
    if (!baseFp.has(n.ctx)) baseFp.set(n.ctx, new Set());
    baseFp.get(n.ctx).add(n.num);
  }
  for (const m of extractNumbers(mdText)) {
    if (baseSet.has(m.num)) continue;
    // 精确指纹命中 → 篡改；否则前缀包含匹配（容忍句首/句尾/标点差异，M3 抽检调优）
    let ctxHits = baseFp.get(m.ctx);
    if (!ctxHits) {
      for (const [k, v] of baseFp) {
        if (v.size && (k.startsWith(m.ctx) || m.ctx.startsWith(k))) { ctxHits = v; break; }
      }
    }
    if (ctxHits && ctxHits.size) {
      issues.push({ code: "D1", severity: "critical",
        item: "数字与基准口径不符：基准为 " + [...ctxHits].join("/") + "，材料出现 " + m.num + "（上下文「" + m.ctx.split("<N>").join("□") + "」）",
        suggestion: "对照参与边界卡/简历修正为基准口径" });
    } else if (isMetricShape(m.ctx)) {
      issues.push({ code: "D1", severity: "critical",
        item: "出现基准外指标数字：" + m.num + "（上下文「" + m.ctx.split("<N>").join("□") + "」）",
        suggestion: "该指标不在基准口径中，删除或改用基准数字" });
    } else if (parseFloat(m.num) >= 2) {
      issues.push({ code: "D1", severity: "warn",
        item: "出现基准外裸数字：" + m.num + "（上下文「" + m.ctx.split("<N>").join("□") + "」）",
        suggestion: "核对是否需与基准口径保持一致" });
    }
  }
  return issues;
}

// ---------- D2 项目真实性 ----------
// 从参与边界卡提取各版本专属项目名：A 版（RAG/Agent 应用类）与 B 版（推理/部署/量化类）
function extractCardProjects(card) {
  const sets = { A: new Set(), B: new Set() };
  const lines = String(card || "").split("\n");
  let zone = null; // "A" | "B" | null
  for (const line of lines) {
    if (/^#{2,3}\s+二、简历 A 版/.test(line)) zone = "A";
    else if (/^#{2,3}\s+三、简历 B 版/.test(line)) zone = "B";
    else if (/^#{2,3}\s+四、/.test(line)) zone = null;
    if (!zone) continue;
    const m = /^#{2,3}\s+(?:项目[一二三四五六七八九十\d]+[：:]\s*)?(.+?)\s*（/.exec(line.trim());
    if (m) sets[zone].add(m[1].trim());
    // 兜底："### 2.2 项目一：浙江电信私有化知识库问答系统（RAG）" 的另一种形态
    const m2 = /^#{2,3}\s+[\d.]+\s*项目[一二三四五六七八九十\d]+[：:]\s*(.+?)\s*（/.exec(line.trim());
    if (m2) sets[zone].add(m2[1].trim());
  }
  return sets;
}
// 从材料提取「项目」标题（## / ### 下、含项目关键词的行）
function extractProjectTitles(mdText) {
  const out = [];
  const re = /^#{2,4}\s+([^#\n]+)$/gm;
  let m;
  while ((m = re.exec(String(mdText || "")))) {
    const t = m[1].trim();
    if (/项目|系统|平台|服务化|RAG|Agent|智能体|问答|推理|量化|部署/.test(t)) out.push(t);
  }
  return out;
}
// ver：'A' | 'B' | ''（'' = Web 上传简历，无法版本判定，仅检查编造）
function checkProjectTruth(card, mdText, ver, file) {
  const issues = [];
  const hasCard = !!card && String(card).trim();
  if (!hasCard) return issues;
  const projSets = extractCardProjects(card);
  const allKnown = new Set([...projSets.A, ...projSets.B]);
  for (const title of extractProjectTitles(mdText)) {
    // 编号引用（项目1/项目2）不判编造
    if (/^项目\d+$/.test(title)) continue;
    // 章节/页眉/编号引用式标题不判编造（M3 抽检调优：避免把「项目深挖」「4.1 总体策略」「XX公司—面试主线」「项目」等误判为编造项目）
    if (/^项目$|项目深挖|讲述|框架|策略|总体|主线|STAR|面试|简历编号|速查|防串号|串号|【】|^##|^###|[：:—·]|^\s*[\d.]+|^[一二三四五六七八九十]+[、．.]/.test(title)) continue;
    const isKnown = [...allKnown].some(k => title.indexOf(k) >= 0 || k.indexOf(title) >= 0);
    if (!isKnown) {
      // 明显是项目名（含 系统/平台/服务化/Agent 等）但不在基准 → 编造 critical
      issues.push({ code: "D2", severity: "critical", item: "材料出现基准外项目「" + title + "」，参与边界卡/简历中不存在",
        suggestion: "删除该项目或改为基准内经历" });
      continue;
    }
    if (ver === "A" && [...projSets.B].some(k => title.indexOf(k) >= 0) && ![...projSets.A].some(k => title.indexOf(k) >= 0)) {
      issues.push({ code: "D2", severity: "warn", item: "A 版材料出现 B 版专属项目「" + title + "」（推理/部署/量化类）",
        suggestion: "该项目属于简历 B 版（推理部署方向），请从 A 版材料移除或仅一句话带过" });
    }
    if (ver === "B" && [...projSets.A].some(k => title.indexOf(k) >= 0) && ![...projSets.B].some(k => title.indexOf(k) >= 0)) {
      issues.push({ code: "D2", severity: "warn", item: "B 版材料出现 A 版专属项目「" + title + "」（RAG/Agent 应用类）",
        suggestion: "该项目属于简历 A 版（应用/Agent 方向），请从 B 版材料移除或仅一句话带过" });
    }
  }
  return issues;
}

// ---------- D4 结构完整性 ----------
// 截断特征（与 pipeline.detectTruncation 同源）：乱码 / 孤立序号 / 空列表项 / 05 章节标记缺失
function detectTruncation(name, md) {
  const problems = [];
  if (!md || !String(md).trim()) { problems.push("内容为空"); return problems; }
  if (md.indexOf("\uFFFD") >= 0) problems.push("含乱码字符（输出中断残留）");
  if (/^\s*\d+[\.、)]?\s*$/m.test(md)) problems.push("列表项仅有序号、内容缺失（输出中断）");
  if (/^\s*[-*]\s*$/m.test(md)) problems.push("列表项空内容（输出中断）");
  if (name === "05_面经分析与面试题库") {
    const marks = ["## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、", "## 八、", "### 7.1", "### 7.2", "### 7.3"];
    const missing = marks.filter(mk => md.indexOf(mk) < 0);
    if (missing.length) problems.push("缺少章节标记：" + missing.join("、"));
  }
  return problems;
}
function checkStructure(name, mdText, file) {
  const issues = [];
  const md = String(mdText || "");
  const trunc = detectTruncation(name, md);
  for (const t of trunc) issues.push({ code: "D4", severity: "critical", item: "结构异常：" + t, suggestion: "重新生成该文件" });
  // 一级标题违例：SYSTEM_GEN 要求标题从 ## 开始
  const m1 = /^# [^\n]+/m.exec(md);
  if (m1) issues.push({ code: "D4", severity: "warn", item: "出现一级标题「" + m1[0].trim() + "」，规范要求从 ## 开始", suggestion: "降级为 ## 标题" });
  // 代码围栏破坏：围栏未配对
  const fences = (md.match(/```/g) || []).length;
  if (fences % 2 !== 0) issues.push({ code: "D4", severity: "critical", item: "代码围栏 ``` 未配对（" + fences + " 个），可能破坏后续渲染", suggestion: "补齐围栏" });
  // 组件框架缺失（intro/star 结构固化）
  const r = components.validate(name, md);
  if (!r.ok) issues.push({ code: "D4", severity: "warn", item: "缺少组件框架标记：" + r.missing.join("、"), suggestion: "按组件框架补全结构" });
  return issues;
}

// ---------- D5 术语一致性 ----------
// 精确大写出现 > 0 且忽略大小写计数大于精确计数 → 混用（小写变体并存）
function checkGlossary(mdText, file) {
  const issues = [];
  const md = String(mdText || "");
  for (const term of Object.keys(GLOSSARY)) {
    if (!/[A-Za-z]/.test(term)) continue; // 纯中文术语无大小写问题
    const re = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g");
    const rei = new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    const exact = (md.match(re) || []).length;
    const loose = (md.match(rei) || []).length;
    if (exact > 0 && loose > exact) {
      issues.push({ code: "D5", severity: "warn",
        item: "术语拼写混用：材料同时存在「" + term + "」与其小写/变体写法（共 " + loose + " 处，大写 " + exact + " 处）",
        suggestion: "统一为「" + term + "」" });
    }
  }
  return issues;
}

// ---------- 汇总 ----------
// fileNames：待审核文件名数组（默认白名单）；outDir：材料目录
// 返回 { issues:[{file,code,severity,item,suggestion}], critical:[], warn:[], ok }
function runRuleCheck(outDir, card, resumeText, ver, fileNames) {
  const issues = [];
  const baseText = [card, resumeText].filter(Boolean).join("\n");
  const names = Array.isArray(fileNames) && fileNames.length ? fileNames : ["面试主线", "01_自我介绍", "02_项目深挖", "附录_数字口径"];
  for (const name of names) {
    const p = path.join(outDir, name + ".md");
    if (!fs.existsSync(p)) continue;
    let md;
    try { md = fs.readFileSync(p, "utf8"); } catch (e) { continue; }
    issues.push(...checkDigitConsistency(baseText, md, name));
    issues.push(...checkProjectTruth(card, md, ver, name));
    issues.push(...checkStructure(name, md, name));
    issues.push(...checkGlossary(md, name));
  }
  const critical = issues.filter(i => i.severity === "critical");
  const warn = issues.filter(i => i.severity === "warn");
  return { issues, critical, warn, ok: critical.length === 0 };
}

module.exports = { runRuleCheck, detectTruncation, checkDigitConsistency, checkProjectTruth, checkStructure, checkGlossary, extractNumbers, extractProjects: extractCardProjects };
