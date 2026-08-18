"""prep_agent 质量回路配置（移植 MS quality_config.js · SOP-07）。

环境变量：
  PREP_QUALITY_ROUNDS  轮次上限（默认 2，0=关闭，夹在 0~3）
  PREP_QUALITY_MODE    on | warn-only | off（默认 on；warn-only 只展示不阻断）
  PREP_QUALITY_FILES   白名单文件名（逗号分隔，默认面试主线/01_自我介绍/02_项目深挖/附录_数字口径）
优先级：环境变量为基础，state.quality 的 mode/maxRounds/reviewFiles 可覆盖（大脑透传前端配置）。
"""
from __future__ import annotations

import os
from typing import Any

DEFAULT_FILES = ["面试主线", "01_自我介绍", "02_项目深挖", "附录_数字口径"]
VALID_MODES = ["on", "warn-only", "off"]


def get_quality_config(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or dict(os.environ)
    raw = env.get("PREP_QUALITY_ROUNDS", "")
    try:
        max_rounds = max(0, min(3, int(raw)))
    except (TypeError, ValueError):
        max_rounds = 2
    mode = str(env.get("PREP_QUALITY_MODE", "on")).lower().strip()
    if mode not in VALID_MODES:
        mode = "on"
    review_files = DEFAULT_FILES
    raw_files = [s.strip() for s in env.get("PREP_QUALITY_FILES", "").split(",") if s.strip()]
    if raw_files:
        review_files = raw_files
    return {"enabled": max_rounds > 0 and mode != "off",
            "max_rounds": max_rounds, "review_files": review_files, "mode": mode}


def merge_quality_cfg(base: dict[str, Any], q: dict[str, Any] | None) -> dict[str, Any]:
    q = q or {}
    cfg = {k: base.get(k) for k in ("max_rounds", "mode", "review_files")}
    if str(q.get("mode", "")).lower() in VALID_MODES:
        cfg["mode"] = str(q.get("mode")).lower()
    if isinstance(q.get("max_rounds"), int):
        cfg["max_rounds"] = max(0, min(3, q["max_rounds"]))
    if isinstance(q.get("reviewFiles"), list) and q["reviewFiles"]:
        cfg["review_files"] = [str(s) for s in q["reviewFiles"]]
    cfg["enabled"] = cfg["max_rounds"] > 0 and cfg["mode"] != "off"
    return cfg
