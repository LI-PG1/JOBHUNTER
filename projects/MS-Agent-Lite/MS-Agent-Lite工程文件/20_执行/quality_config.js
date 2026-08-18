// quality_config.js — M3 质量回路配置（SOP-07）
// 环境变量：
//   MS_AGENT_QUALITY_ROUNDS  轮次上限（默认 2，0=关闭，夹在 0~3）
//   MS_AGENT_QUALITY_MODE    on | warn-only | off（默认 on；warn-only 只展示不阻断）
//   MS_AGENT_QUALITY_FILES   白名单文件名（逗号分隔，默认面试主线/01_自我介绍/02_项目深挖/附录_数字口径）
// 优先级：环境变量为基础，runGenerate input.quality 的 mode/maxRounds/reviewFiles 可覆盖（server 透传前端配置）
const DEFAULT_FILES = ["面试主线", "01_自我介绍", "02_项目深挖", "附录_数字口径"];
const VALID_MODES = ["on", "warn-only", "off"];

function getQualityConfig(env) {
  env = env || {};
  const raw = parseInt(env.MS_AGENT_QUALITY_ROUNDS || "", 10);
  const maxRounds = Number.isInteger(raw) ? Math.max(0, Math.min(3, raw)) : 2;
  let mode = String(env.MS_AGENT_QUALITY_MODE || "on").toLowerCase().trim();
  if (VALID_MODES.indexOf(mode) < 0) mode = "on";
  let reviewFiles = DEFAULT_FILES;
  try {
    const rawFiles = String(env.MS_AGENT_QUALITY_FILES || "").split(",").map(s => s.trim()).filter(Boolean);
    if (rawFiles.length) reviewFiles = rawFiles;
  } catch (e) { /* 保持默认 */ }
  return { enabled: maxRounds > 0 && mode !== "off", maxRounds, reviewFiles, mode };
}

// 合并 input.quality 覆盖：{ mode?, maxRounds?, reviewFiles? } 仅接受合法值
function mergeQualityCfg(base, input) {
  const q = input && typeof input === "object" ? input : {};
  const cfg = { maxRounds: base.maxRounds, mode: base.mode, reviewFiles: base.reviewFiles };
  if (VALID_MODES.indexOf(String(q.mode).toLowerCase()) >= 0) cfg.mode = String(q.mode).toLowerCase();
  if (Number.isInteger(q.maxRounds)) cfg.maxRounds = Math.max(0, Math.min(3, q.maxRounds));
  if (Array.isArray(q.reviewFiles) && q.reviewFiles.length) cfg.reviewFiles = q.reviewFiles.map(String);
  cfg.enabled = cfg.maxRounds > 0 && cfg.mode !== "off";
  return cfg;
}

module.exports = { getQualityConfig, mergeQualityCfg, DEFAULT_FILES, VALID_MODES };
