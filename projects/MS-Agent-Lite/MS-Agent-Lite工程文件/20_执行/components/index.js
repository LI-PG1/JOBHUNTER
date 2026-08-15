// components/index.js — 通用内容组件注册表（SOP-01/02：一次维护，所有公司/岗位复用）
// 组件 = 「框架（结构固化）+ 提示（prompt hint 注入）+ 校验（verify 用）+ 兜底（LLM 失败占位）」
// 新增组件：在 components/ 下新建模块并加入 REGISTRY 即可，pipeline/verify 自动生效。
const intro = require('./intro.js');
const star = require('./star.js');

const REGISTRY = [intro, star];

// 按目标文件查组件（pipeline FILES 名称精确匹配）
function forTarget(fileName) {
  return REGISTRY.find(c => c && c.targets && c.targets.indexOf(fileName) >= 0) || null;
}

// 合并提示：组件框架 + 原 hint，注入生成 prompt（减少结构漂移，保证输出一致性）
function buildHint(fileName, originalHint) {
  const c = forTarget(fileName);
  if (!c || !c.framework) return originalHint;
  return String(originalHint || '') + '\n\n【组件框架（必须遵守）】\n' + c.framework;
}

// 兜底模板：LLM 生成失败时写盘，保证 build/verify 不中断（SOP-05）；无兜底返回 null
function fallbackFor(fileName) {
  const c = forTarget(fileName);
  return c && c.fallback ? c.fallback() : null;
}

// 结构校验：返回 { ok, missing: [] }（verify.js SOP-CHECK 用）
function validate(fileName, content) {
  const c = forTarget(fileName);
  if (!c || !c.requiredMarkers || !c.requiredMarkers.length) return { ok: true, missing: [] };
  const missing = c.requiredMarkers.filter(m => content.indexOf(m) < 0);
  return { ok: missing.length === 0, missing };
}

module.exports = { REGISTRY, forTarget, buildHint, fallbackFor, validate };
