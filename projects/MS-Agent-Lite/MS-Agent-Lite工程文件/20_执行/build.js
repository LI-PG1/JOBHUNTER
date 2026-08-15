// build.js — 面试准备.html 生成器（v2 模板装配模式）
// 架构：内容组装（md 读取/拆分/重组） + 共享术语表（glossary.js） + 静态模板装配（templates/skeleton.html）
// 内容源：00_公司背景(模板) / 面试主线 / 01~04 / 05_面经(拆分融入) / 附录_数字口径
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const scriptDir = path.dirname(process.argv[1]);
const comp = process.argv[2] || '示例-公司';
const resumeVer = (process.argv[3] || '').toUpperCase(); // 第三参数：简历版本（旧 A/B 简写，或 10_知识库/简历基准 下的文件名，开始前用户指定）
const RESUME_INFO = { 'A': '简历 A 版 · 应用/Agent/RAG', 'B': '简历 B 版 · 推理/部署/量化' };
const resumeTag = RESUME_INFO[resumeVer] || (resumeVer ? '简历版本：' + resumeVer : ''); // 未指定则不显示版本标签
const contact = '联系作者 llxstupg@163.com'; // 固定水印（v0.4.14 起不再由用户填写）：统一注入结果文件页眉与页脚
// 联系方式 HTML 转义（防注入模板）
const escHtml = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const contactStr = contact ? escHtml(contact) : '';
// 页眉：顶栏右侧紧凑显示「📮 联系方式 · 祝面试顺利」（无联系方式时为空，模板占位符替换为空串）
const contactHead = contactStr ? '📮 ' + contactStr + ' · 祝面试顺利' : '';
// 页脚：独立卡片显示联系方式 + 祝福语
const contactFoot = contactStr
  ? '<div class="page-footer"><div class="pf-box">' +
    '<div class="pf-contact">📮 联系方式：' + contactStr + '</div>' +
    '<div class="pf-bless">祝面试顺利，早日收获心仪 Offer！</div>' +
    '</div></div>'
  : '';
const root = path.resolve(scriptDir, '..');
const mdDir = path.join(root, '30_产出', '面试材料', comp);
const read = n => fs.readFileSync(path.join(mdDir, n), 'utf8');

// ---------- 读取 md ----------
const mainMd = read('面试主线.md');
const s1 = read('01_自我介绍.md');
const s2 = read('02_项目深挖.md');
const s3 = read('03_技术场景题.md');
const s4 = read('04_反问环节.md');
const s5 = read('05_面经分析与面试题库.md');
const app = read('附录_数字口径.md');

// ---------- 截取工具 ----------
function slice(md, start, end) {
  const s = md.indexOf(start);
  if (s < 0) throw new Error('start marker not found: ' + start);
  const e = end ? md.indexOf(end, s) : md.length;
  if (e < 0) throw new Error('end marker not found: ' + end);
  return md.slice(s, e);
}
// P1-7 容错：LLM 输出偶尔缺章节标题/分隔线。缺失时降级为「跳过该段 + 记录告警」，
// 而不是整批 build 失败——核心材料仍可产出，缺失章节在 HTML 顶部横幅与控制台提示
const SKIPPED = []; // 被跳过（缺标记）的 05 章节，用于 HTML 横幅告警
function sliceSafe(md, start, end, label) {
  try { return slice(md, start, end); }
  catch (e) { SKIPPED.push(label); return ''; }
}
// LLM 生成的 05 文件章节分隔线（---）可能缺失，优先精确匹配（含 ---），失败回退到仅章节标题
function sliceF(md, start, exactEnd, fallbackEnd, label) {
  try { return slice(md, start, exactEnd); }
  catch (e) {
    try { return slice(md, start, fallbackEnd); }
    catch (e2) { SKIPPED.push(label); return ''; }
  }
}
// 05 文件「## 一、<公司名> 面试流程与特点」标题中公司名可能缺失/写成占位符（如 <公司名>），
// 用正则匹配「## 一、…面试流程与特点」做容错，不要求与 comp 精确一致
function sliceFlow(md) {
  const m = md.match(/^## 一、[\s\S]*?面试流程与特点/m);
  if (!m) throw new Error('start marker not found: ## 一、* 面试流程与特点');
  // 终点：优先取「## 二、针对你的面试策略调整」标题之后的第一个子标题（### 2.x）或「## 三」，
  // 使「## 二」的标题与引言被完整保留（审查发现此前整节静默丢失），且不吞掉 2.1/2.3 小节正文（避免与 epCpp/epProj 重复）
  let end = md.length;
  const two = md.indexOf('## 二、针对你的面试策略调整', m.index);
  if (two >= 0) {
    const sub = md.indexOf('### ', two);
    const h3 = md.indexOf('## 三', two);
    if (sub > 0) end = Math.min(end, sub);
    if (h3 > 0) end = Math.min(end, h3);
  } else {
    // 无「## 二」（异常输出）：回退到 2.1 或「## 三」，仅保留「## 一」
    const cpp = md.indexOf('### 2.1 C++ 问题应对', m.index);
    const h3 = md.indexOf('## 三', m.index);
    if (cpp > 0) end = cpp;
    else if (h3 > 0) end = h3;
  }
  return md.slice(m.index, end);
}
function demote(md) {
  return md
    .replace(/^#### /gm, '##### ')
    .replace(/^### /gm, '#### ')
    .replace(/^## /gm, '### ')
    .replace(/^# /gm, '## ');
}

// ---------- 面经拆分（P1-7：任一章节缺标记 → 跳过该段并记入 SKIPPED，不阻断 build） ----------
let epFlow = '';
try { epFlow = sliceFlow(s5); } catch (e) { SKIPPED.push('一、面试流程与特点'); }
const epCpp   = sliceSafe(s5, '### 2.1 C++ 问题应对', '### 2.3 项目深挖的新认知', '2.1 C++ 问题应对');
const epProj  = sliceF(s5, '### 2.3 项目深挖的新认知', '---\n\n## 三、AI Agent 工程化面试高频题', '## 三、AI Agent 工程化面试高频题', '2.3 项目深挖的新认知');
const epAgent = sliceSafe(s5, '## 三、AI Agent 工程化面试高频题', '## 四、RAG 面试高频题', '三、AI Agent 工程化面试高频题');
const epRag   = sliceSafe(s5, '## 四、RAG 面试高频题', '## 五、大模型部署面试高频题', '四、RAG 面试高频题');
const epDeploy= sliceSafe(s5, '## 五、大模型部署面试高频题', '## 六、自动驾驶领域知识速补', '五、大模型部署面试高频题');
const epDomain= sliceSafe(s5, '## 六、自动驾驶领域知识速补', '## 七、面试各阶段策略', '六、自动驾驶领域知识速补');
const epRound1= sliceSafe(s5, '### 7.1 一面策略', '### 7.2 二面策略', '7.1 一面策略');
const epRound2= sliceSafe(s5, '### 7.2 二面策略', '### 7.3 HRBP面策略', '7.2 二面策略');
const epHr    = sliceF(s5, '### 7.3 HRBP面策略', '---\n\n## 八、面试核心差异点', '## 八、面试核心差异点', '7.3 HRBP面策略');
const epCore  = sliceSafe(s5, '## 八、面试核心差异点', null, '八、面试核心差异点');

// ---------- 重组 ----------
// 空内容（被跳过的章节）不输出空标题：避免 HTML 中出现孤立的「## xxx」小节（审查发现空 epX 保留空标题）
const block = (title, content) =>
  (content && content.trim()) ? '\n\n---\n\n## ' + title + '\n\n' + demote(content) : '';

let mainNew = mainMd;
if (mainMd.indexOf('## 三、匹配度分析') >= 0) {
  mainNew = mainMd.replace('## 三、匹配度分析',
    (epFlow && epFlow.trim() ? '### 面经参考：' + comp + ' 真实面试流程\n\n' + demote(epFlow) + '\n\n---\n\n' : '') +
    '## 三、匹配度分析');
} else {
  // 标记缺失时记入 SKIPPED（审查发现此前 replace 静默空转、无任何提示）
  SKIPPED.push('面试主线：缺少「## 三、匹配度分析」标记，面经参考未能注入');
}

const s1new = s1 + block('一面策略（面经参考）', epRound1);

const s2new = s2
  + block('项目深挖进阶（面经启示）', epProj)
  + block('二面实战策略', epRound2)
  + block('工程颗粒度（决胜点）', epCore);

const s3new = s3
  + block('C++ 问题应对（' + comp + ' 高频考 C++，你是 Python）', epCpp)
  + block('AI Agent 工程化高频题（你的强项领域）', epAgent)
  + block('RAG 高频题（你的强项领域）', epRag)
  + block('大模型部署高频题', epDeploy)
  + block('自动驾驶领域知识速补', epDomain);

const s4new = s4 + block('HRBP 面策略（面经参考）', epHr);

// 更新主线文件索引表
const idxStart = mainNew.indexOf('| 文件 | 内容 |');
if (idxStart >= 0) {
  const tailMatch = mainNew.slice(idxStart).match(/^---\s*$/m);
  const idxEnd = tailMatch ? idxStart + tailMatch.index : mainNew.length;
  const tail = idxEnd >= 0 ? mainNew.slice(idxEnd) : '';
  const mdPath = p => 'file:///' + mdDir.replace(/\\/g, '/') + '/' + p;
  const newIndex = '| 文件 | 内容 |\n|------|------|\n'
    + '| [00_公司背景.md](' + mdPath('00_公司背景.md') + ') | ' + comp + ' 公司/业务/技术路线/发展方向 |\n'
    + '| [面试主线.md](' + mdPath('面试主线.md') + ') | 岗位分析+面试流程+匹配度+策略 |\n'
    + '| [01_自我介绍.md](' + mdPath('01_自我介绍.md') + ') | 自我介绍话术 + 一面策略 |\n'
    + '| [02_项目深挖.md](' + mdPath('02_项目深挖.md') + ') | 项目 STAR + 追问防守 + 二面策略 |\n'
    + '| [03_技术场景题.md](' + mdPath('03_技术场景题.md') + ') | 领域问题 + 场景题 + 高频题库 + 知识速补 |\n'
    + '| [04_反问环节.md](' + mdPath('04_反问环节.md') + ') | 反问问题 + HRBP 面策略 |\n'
    + '| [附录_数字口径.md](' + mdPath('附录_数字口径.md') + ') | 必须一致的数字 |\n\n';
  mainNew = mainNew.slice(0, idxStart) + newIndex + tail;
}

// ---------- 公司背景：优先读取 10_知识库/岗位画像/<公司>*.md（投递前用联网搜索+面经塑造），未写时回退内置模板 ----------
const portraitFiles = (() => { try { return fs.readdirSync(path.join(root, '10_知识库', '岗位画像')); } catch (e) { return []; } })()
  .filter(f => /\.md$/i.test(f) && f.indexOf(comp) === 0).sort();
let companyMd;
if (portraitFiles.length > 0) {
  companyMd = fs.readFileSync(path.join(root, '10_知识库', '岗位画像', portraitFiles[0]), 'utf8');
} else {
companyMd = `# 00 ${comp} 公司与业务背景

> 面试前必读：展示岗位理解深度的关键素材。HRBP 面「为什么选我们」、反问环节、自我介绍里的「我了解贵司」都用得上。
> 未找到 10_知识库/岗位画像/<公司>*.md：请先用联网搜索 + 公开面经为该岗位创建画像（参照 10_知识库/岗位画像/_模板-公司-岗位.md），否则以下为占位信息。

---

## 一、公司概况

> 待补充：公司定位 / 成立时间 / 规模 / 主要产品线（来源：岗位画像）
> 待补充官网：公司官网 <code>https://（以官网为准）</code> ／ 主要业务线官网 <code>https://（以官网为准）</code>——面试前务必点开核对，HRBP 面「为什么选我们」直接引用官网口径更有说服力。

## 二、技术/业务方向

> 待补充：技术路线、产品方向、面试常考业务点（来源：岗位画像）

## 三、面试怎么用这些信息

| 场景 | 用法 |
|------|------|
| 自我介绍 | 结合岗位画像中公司技术路线，讲自己的迁移经验 |
| HRBP 面 | 「为什么选我们」→ 公司定位 + 业务方向，证明做过功课 |
| 反问环节 | 基于岗位画像中的技术方向提问 |
`;
}

// ---------- 组装文件列表 ----------
const files = [
  { name: '00_公司背景', md: companyMd },
  { name: '面试主线', md: mainNew },
  { name: '01_自我介绍', md: s1new },
  { name: '02_项目深挖', md: s2new },
  { name: '03_技术场景题', md: s3new },
  { name: '04_反问环节', md: s4new },
  { name: '附录_数字口径', md: app }
];

// ---------- 面试流程环节定义 ----------
const phases = [
  { id: 'prep',    no: '01', title: '面试准备', sub: '公司背景 × 岗位主线，先建立全局认知', files: ['00_公司背景', '面试主线'] },
  { id: 'intro',   no: '02', title: '自我介绍', sub: '90 秒完整版 + 60 秒精简版 + 一面策略', files: ['01_自我介绍'] },
  { id: 'project', no: '03', title: '项目经验', sub: '简历 5 项目 STAR · 追问防守 · 简历外对口补充', files: ['02_项目深挖'] },
  { id: 'tech',    no: '04', title: '技术问答', sub: '领域问题 · 场景案例分析 · 高频题库', files: ['03_技术场景题'] },
  { id: 'qa',      no: '05', title: '反问环节', sub: '精选反问问题 · HRBP 面策略', files: ['04_反问环节'] },
  { id: 'appendix',no: '06', title: '数字速查', sub: '口径一致，面试防矛盾', files: ['附录_数字口径'] },
  { id: 'followup',no: '07', title: '面试后跟进', sub: '面试复盘 · 关键决策记录', files: [] }
];

// ---------- 术语表（tooltip 解释） ----------
const { GLOSSARY, EXTRA } = require('./glossary.js');

// ---------- 生成 HTML ----------
// P1-7：被跳过章节的可见告警（新手用户不看控制台，横幅直接显示在页面顶部）
const buildWarnHtml = SKIPPED.length
  ? '<div class="build-warn"><b>⚠ 提示：</b>以下章节因 LLM 输出缺少标题标记被跳过，请检查「05_面经分析与面试题库.md」后重试：' + SKIPPED.join('、') + '</div>'
  : '';
const filesJson = JSON.stringify(files).replace(/</g, '\\u003c');
const glossaryJson = JSON.stringify(Object.assign({}, GLOSSARY, EXTRA)).replace(/</g, '\\u003c');
const phasesJson = JSON.stringify(phases);


// ---------- 增量构建（v2）：源 md 内容未变则跳过渲染（SOP-02 检查点） ----------
const OUT_PATH = path.join(mdDir, comp + '面试准备.html');
const CACHE_PATH = path.join(mdDir, '.build-cache.json');
const contentHash = crypto.createHash('sha256').update(JSON.stringify(files) + '|' + contact).digest('hex');
let cached = null;
try { cached = JSON.parse(fs.readFileSync(CACHE_PATH, 'utf8')); } catch (e) { cached = null; }
const force = process.argv.indexOf('--force') >= 0;
if (!force && cached && cached.hash === contentHash && fs.existsSync(OUT_PATH)) {
  console.log('SKIP: 源 md 无变化，跳过渲染（--force 强制重建）');
  console.log('OK, bytes:', fs.statSync(OUT_PATH).size);
  process.exit(0);
}

// ---------- 模板装配（v2 架构：模板/组件/术语表分离，SOP-02） ----------
// 静态骨架（CSS + DOM + 渲染 JS）一次维护于 20_执行/templates/skeleton.html，
// 本步骤仅注入内容数据，消除每次重复渲染同一框架的计算开销，保证输出一致性。
const SKELETON_PATH = path.join(scriptDir, 'templates', 'skeleton.html');
const skeleton = fs.readFileSync(SKELETON_PATH, 'utf8');
const resumeTagHtml = resumeTag ? ' ｜ ' + resumeTag : '';
const html = skeleton
  .split('{{COMP}}').join(comp)
  .split('{{RESUME_TAG}}').join(resumeTagHtml)
  .split('{{CONTACT_HEAD}}').join(contactHead)
  .split('{{CONTACT_FOOT}}').join(contactFoot)
  .split('{{FILES_JSON}}').join(filesJson)
  .split('{{GLOSSARY_JSON}}').join(glossaryJson)
  .split('{{PHASES_JSON}}').join(phasesJson)
  .split('{{BUILD_WARN_HTML}}').join(buildWarnHtml);

fs.writeFileSync(OUT_PATH, html, 'utf8');
fs.writeFileSync(CACHE_PATH, JSON.stringify({ hash: contentHash, builtAt: new Date().toISOString() }), 'utf8');
if (SKIPPED.length) console.log('WARN: skipped sections (missing markers): ' + SKIPPED.join(', '));
console.log('OK, bytes:', html.length);
