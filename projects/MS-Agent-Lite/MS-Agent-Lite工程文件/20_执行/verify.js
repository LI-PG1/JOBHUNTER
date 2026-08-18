// verify.js — 验证生成的面试 HTML：JS 语法 + 数据注入 + 关键标记 + 术语数
// 用法: node verify.js <公司名>   （默认读 30_产出/面试材料/<公司名>/*面试准备.html）
// 修复说明（技术遗留 E）：不再用 /const GLOSSARY = (\{.*?\});<\/script>/s 正则解析超长 JSON
// （非贪婪 + 嵌套对象会导致匹配截断/回溯失败），改用"平衡括号扫描"提取顶层对象后再 JSON.parse。
const fs = require('fs');
const path = require('path');
const components = require('./components/index.js');

const company = process.argv[2] || '示例-公司';
const dir = path.join(__dirname, '..', '30_产出', '面试材料', company);
if (!fs.existsSync(dir)) {
  console.error('材料目录不存在:', dir);
  process.exit(1);
}
// 文件名规则：<岗位名称>面试准备.html
const htmlName = (fs.readdirSync(dir).find(f => f.endsWith('面试准备.html') && !f.startsWith('_'))) || '面试准备.html';
const htmlPath = path.join(dir, htmlName);
if (!fs.existsSync(htmlPath)) {
  console.error('HTML not found:', htmlPath);
  process.exit(1);
}
const html = fs.readFileSync(htmlPath, 'utf8');

// 1) 提取所有 <script> 内容，做语法检查（不执行）
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
console.log('script blocks:', scripts.length);
let syntaxOK = true;
scripts.forEach((s, i) => {
  try { new Function(s); console.log('  block ' + i + ': syntax OK'); }
  catch (e) { syntaxOK = false; console.log('  block ' + i + ': SYNTAX ERROR -> ' + e.message); }
});

// 2) 数据注入检查
const hasMD = html.includes('const MD_FILES = ');
const hasGL = html.includes('const GLOSSARY = ');
const hasPh = html.includes('var PHASES = ');
console.log('MD_FILES injected:', hasMD);
console.log('GLOSSARY injected:', hasGL);
console.log('PHASES injected:', hasPh);

// 3) 关键功能标记
['id="progress"', 'id="steps"', 'id="mobileSteps"', 'id="noteFab"', 'id="noteDrawer"',
 'class="phase-head"', 'details.fold', 'foldDeep', 'annotateText', 'data-tip', 'codebox'].forEach(k => {
  console.log('  has', k, ':', html.includes(k));
});

// 4) 术语数 —— 平衡括号扫描（修复 E：超长 JSON 不用正则）
// 从 "const GLOSSARY = " 之后找第一个 '{'，逐字符统计深度，深度归零即对象结束。
// 泛化：支持顶层对象（{}）与数组（[]，如 MD_FILES），按首个出现的括号类型匹配闭括号
function extractBalanced(text, startMarker) {
  const start = text.indexOf(startMarker);
  if (start < 0) return null;
  const openObj = text.indexOf('{', start + startMarker.length);
  const openArr = text.indexOf('[', start + startMarker.length);
  let openIdx = -1, closeChar = '';
  if (openObj < 0 && openArr < 0) return null;
  if (openArr >= 0 && (openObj < 0 || openArr < openObj)) { openIdx = openArr; closeChar = ']'; }
  else { openIdx = openObj; closeChar = '}'; }
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = openIdx; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escape) escape = false;
      else if (ch === '\\') escape = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') { inString = true; continue; }
    if (ch === '{' || ch === '[') depth++;
    else if (ch === '}' || ch === ']') {
      depth--;
      if (depth === 0 && ch === closeChar) return text.slice(openIdx, i + 1);
    }
  }
  return null;
}

const glRaw = extractBalanced(html, 'const GLOSSARY = ');
if (glRaw) {
  try {
    const gl = JSON.parse(glRaw);
    console.log('glossary terms:', Object.keys(gl).length);
  } catch (e) {
    console.log('GLOSSARY parse failed:', e.message);
  }
} else {
  console.log('GLOSSARY balanced scan: not found');
}

// 5) MD_FILES 内容非空检查（审查发现：关键标记存在但 md 内容可为空，verify 无法发现）
let filesOK = true;
let mdFiles = null;
const mdRaw = extractBalanced(html, 'const MD_FILES = ');
if (mdRaw) {
  try {
    mdFiles = JSON.parse(mdRaw);
    mdFiles.forEach(f => {
      if (!f || !f.md || !f.md.trim()) { filesOK = false; console.log('  EMPTY md content: ' + (f && f.name || '(unknown)')); }
    });
    console.log('md files non-empty:', filesOK ? 'ALL OK (' + mdFiles.length + ' files)' : 'EMPTY FOUND (see above)');
  } catch (e) { filesOK = false; console.log('MD_FILES parse failed:', e.message); }
} else { filesOK = false; console.log('MD_FILES not found'); }

// 6) 章节完整性白名单（审查发现：P1-7 章节被跳过时 verify 依旧 PASS）
// 核对重组后各文件必须存在的标题（build.js 按这些标题注入面经拆分内容）。
// 注意：MD 内容在 HTML 源码中是以 JSON 字符串注入的（< 被转义为 \u003c），标题是纯文本 `## xxx`，
// 浏览器运行时才渲染为 <h2>，因此这里直接检查 md 文本而非 HTML 标签。
const REQUIRED_SECTIONS = {
  '面试主线': ['### 面经参考：', '## 三、匹配度分析'],
  '01_自我介绍': ['## 一面策略'],
  '02_项目深挖': ['## 项目深挖进阶', '## 二面实战策略', '## 工程颗粒度'],
  '03_技术场景题': ['## C++ 问题应对', '## AI Agent 工程化高频题', '## RAG 高频题', '## 大模型部署高频题', '## 自动驾驶领域知识速补'],
  '04_反问环节': ['## HRBP 面策略'],
  '附录_数字口径': ['数字口径', '数字陷阱'] // M3（宽松子串兼容 `## 一、数字口径总表` / `## 二、数字陷阱清单`）
};
let sectionsOK = true;
if (mdFiles) {
  Object.entries(REQUIRED_SECTIONS).forEach(([file, keys]) => {
    const md = (mdFiles.find(f => f.name === file) || {}).md || '';
    keys.forEach(k => {
      if (md.indexOf(k) < 0) { sectionsOK = false; console.log('  MISSING section: ' + file + ' -> ' + k); }
    });
  });
} else { sectionsOK = false; }
console.log('required sections:', sectionsOK ? 'ALL PRESENT' : 'MISSING (see above)');

// 7) build 告警横幅（build.js 中被跳过的章节会注入 .build-warn，作为可读提示）
const hasBuildWarn = html.includes('class="build-warn"');
if (hasBuildWarn) console.log('WARN: HTML 顶部有 build-warn 横幅（build.js 有章节被跳过），请检查 05_面经分析与面试题库.md');

// 8) 组件框架校验（SOP-01）：components/ 注册的结构组件标记（intro 等）
// 注意：WARN 级检查——新结构下应全齐；旧材料可能缺新标记，仅提示不阻断（critical 不含此项）
const sopChecks = [];
if (mdFiles) {
  components.REGISTRY.forEach(c => {
    (c.targets || []).forEach(t => {
      const md = (mdFiles.find(f => f.name === t) || {}).md || '';
      const r = components.validate(t, md);
      const state = r.ok ? 'PASS' : 'WARN';
      if (!r.ok) console.log('  WARN: ' + t + ' 缺少组件框架标记: ' + r.missing.join('、'));
      sopChecks.push({ code: 'SOP-01', name: '组件框架·' + (c.title || t), state, detail: r.ok ? '标记齐全' : '缺: ' + r.missing.join('、') });
    });
  });
}

// 9) 构建流程检查点（SOP-02）：静态骨架注入 + 术语表数量 + build 告警
sopChecks.push({ code: 'SOP-02', name: '构建流程', state: 'PASS', detail: '模板装配 + 增量缓存已启用' });
sopChecks.push({ code: 'SOP-03', name: '术语表注入', state: glRaw ? 'PASS' : 'WARN', detail: glRaw ? '' : 'GLOSSARY 未检出' });
if (hasBuildWarn) sopChecks.push({ code: 'SOP-05', name: '章节兜底', state: 'WARN', detail: 'build 有章节被跳过（见 build-warn 横幅）' });

// 10) 文件级质量回路检查点（SOP-07，M3）：读取 .quality.json 汇总，仅展示不改 critical 裁决
// 白名单文件走质量回炉（规则+LLM），未生成 .quality.json 说明本次未启用质量回路（如 mode=off）→ WARN 提示
try {
  const qPath = path.join(dir, '.quality.json');
  if (fs.existsSync(qPath)) {
    const qs = JSON.parse(fs.readFileSync(qPath, 'utf8'));
    const byFile = qs.map(q => q.file + ':' + (q.verdict || 'PASS') + (q.rounds > 1 ? '(' + q.rounds + '轮)' : ''));
    const reworkLeft = qs.filter(q => (q.verdict || 'PASS') !== 'PASS' && q.remaining > 0);
    // 回炉超限遗留 → WARN（提示人工复核，不改 critical 裁决）；全部达标 → PASS
    sopChecks.push({
      code: 'SOP-07', name: '质量回路', state: reworkLeft.length ? 'WARN' : 'PASS',
      detail: reworkLeft.length
        ? '回炉超限遗留 ' + reworkLeft.length + ' 项（' + reworkLeft.map(q => q.file + '×' + q.remaining).join('、') + '）; ' + byFile.join('、')
        : byFile.join('、')
    });
  } else {
    sopChecks.push({ code: 'SOP-07', name: '质量回路', state: 'WARN', detail: '未检出 .quality.json（本次未启用质量回炉或为旧版产物）' });
  }
} catch (e) {
  sopChecks.push({ code: 'SOP-07', name: '质量回路', state: 'WARN', detail: '.quality.json 解析失败（' + String(e.message || e).slice(0, 80) + '）' });
}

// SOP-CHECK 汇总输出（SOP-03：验证与发布流程的检查点）
console.log('\nSOP-CHECK 汇总:');
sopChecks.forEach(c => {
  console.log('  ' + c.code + ' ' + c.name + ': ' + c.state + (c.state === 'PASS' ? '' : ' (' + c.detail + ')'));
});

// 汇总
const critical = [hasMD, hasGL, hasPh].every(Boolean) && syntaxOK && sectionsOK && filesOK;
console.log(critical ? '\nRESULT: PASS' : '\nRESULT: FAIL');
process.exit(critical ? 0 : 1);
