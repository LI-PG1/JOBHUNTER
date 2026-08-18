"""N1 画像解析（parse_profile）。

P0 说明：原实现是 LLM（PROFILE_SYSTEM）解析自由文本画像。P0 线性链无 LLM 判定，
契约输入已含结构化 `profile`，此处直接构造画像卡（card）并做 Gate1 完整性校验。
P1 接入 LLMClient.chat_json 解析自由文本 + 技能 confirmed 防幻觉。
"""
from __future__ import annotations

from typing import Any

from match_agent.state import MatchState


def parse_profile(state: MatchState) -> MatchState:
    """契约输入 → 画像卡 card + Gate1 完整性校验。

    增量更新：card / errors。
    """
    profile = state.get("profile") or {}
    errors = list(state.get("errors") or [])

    card = {
        "background": profile.get("background", ""),
        # 统一 skills 为 list[dict]（含 name）：对齐 JS-Agent 画像卡，decide 的 s.get("name") 可用；
        # 兼容字符串列表输入（judge 双格式兜底）
        "skills": [{"name": s} if isinstance(s, str) else s
                   for s in (profile.get("skills") or [])],
        "experience": list(profile.get("experience") or []),
        "preference": profile.get("preference") or {},
        "city": profile.get("city") or (profile.get("preference") or {}).get("city", ""),
        "degree": profile.get("degree", ""),
    }
    # Gate1 完整性：核心字段缺失仅记录（P0 不中断）
    missing = [k for k in ("skills", "experience") if not card[k]]
    if missing:
        errors.append(f"profile_gate: 缺失字段 {missing}")
    return {**state, "card": card, "errors": errors}
