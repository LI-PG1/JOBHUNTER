"""match_agent 搜索决策器（decide 节点）。

设计依据：《JS搜索回路详细设计.md §3.1》
- `DECIDE_SYSTEM`：LLM 搜索决策提示词
- `decide()`：主入口。LLM 决策 → 校验（schema + converge 护栏）→ 非法/失败降级规则决策器
- `rule_fallback_decision()`：规则降级决策器（机械策略，等价现状顺序执行）
- `validate_decision()`：决策校验（动作枚举 / params 结构 / converge 护栏）

设计要点：LLM 通过 `llm_call` 参数注入（组件独立，不依赖具体 LLM 客户端），
便于测试 mock 与大脑注入真实客户端。
"""

from __future__ import annotations

import json
from typing import Any, Callable

# 动作空间（与文档 §2.3 一致）
ACTIONS = ("rewrite_query", "switch_channel", "deep_dive", "expand", "converge")
CHANNELS = ("招聘平台", "官网", "社区")

DECIDE_SYSTEM = (
    "你是岗位匹配系统的「搜索决策器」。基于当前搜索进度决定下一步行动，输出严格 JSON：\n"
    '{"action":"rewrite_query|switch_channel|deep_dive|expand|converge",'
    '"params":{...},"reason":"决策理由(≤50字)"}\n'
    "动作说明：\n"
    '1. rewrite_query：改写/新增搜索 query（换角度、扩缩小范围），params={"query":"..."}；\n'
    '2. switch_channel：切换渠道（招聘平台/官网/社区），params={"channel":"招聘平台|官网|社区"}；\n'
    '3. deep_dive：对高价值 query 深挖变体，params={"base_query":"...","variant":"..."}；\n'
    '4. expand：基于高匹配岗位扩散同类搜索，params={"seed_entry":"岗位标题或公司名"}；\n'
    "5. converge：认为已收敛，结束搜索，params={}。\n"
    "约束：\n"
    "1. 优先通过 rewrite_query 挖掘未搜索角度，而不是立即 converge；\n"
    "2. 仅当满足「轮数≥最小轮数且收录数≥目标收录数」时才允许 converge；\n"
    "3. 严禁编造不存在的 query 或岗位；城市限定保持与画像一致；\n"
    "4. 只输出一个 JSON 对象，不要输出其他内容。"
)


def build_user_context(card: dict[str, Any], round_stats: list[dict[str, Any]],
                       entries_count: int, target_entries: int,
                       rounds: int, budget_left: int) -> str:
    """构造 decide 的 user 上下文（画像摘要 + 搜索进度 + 收录缺口 + 预算）。"""
    return json.dumps({
        "画像摘要": {
            "城市": card.get("city", ""),
            "技能线": card.get("skill_line", ""),
            "学历": card.get("education", ""),
            "技能": [s.get("name") for s in (card.get("skills") or [])][:8],
        },
        "搜索进度": {
            "已执行轮数": rounds,
            "已收录数": entries_count,
            "目标收录数": target_entries,
            "剩余预算": budget_left,
        },
        "每轮行动统计": round_stats,
    }, ensure_ascii=False)


def validate_decision(obj: Any, *, rounds: int, min_rounds: int,
                      entries_count: int, target_entries: int) -> tuple[bool, str]:
    """校验决策：schema 结构 + converge 护栏。返回 (ok, error)。"""
    if not isinstance(obj, dict):
        return False, "决策不是 JSON 对象"
    action = obj.get("action")
    if action not in ACTIONS:
        return False, f"未知 action: {action!r}"
    params = obj.get("params")
    if not isinstance(params, dict):
        return False, "params 缺失或非对象"
    if action == "rewrite_query":
        if not str(params.get("query", "")).strip():
            return False, "rewrite_query 缺少 params.query"
    elif action == "switch_channel":
        if params.get("channel") not in CHANNELS:
            return False, f"switch_channel 渠道非法: {params.get('channel')!r}"
    elif action == "deep_dive":
        if not str(params.get("base_query", "")).strip():
            return False, "deep_dive 缺少 params.base_query"
    elif action == "expand":
        if not str(params.get("seed_entry", "")).strip():
            return False, "expand 缺少 params.seed_entry"
    elif action == "converge":
        if not (rounds >= min_rounds and entries_count >= target_entries):
            return False, (
                f"converge 不满足收敛护栏（rounds={rounds}≥{min_rounds}？"
                f" entries={entries_count}≥{target_entries}？）"
            )
    return True, ""


def rule_fallback_decision(queries: list[str], executed: set[str],
                           rounds: int, min_rounds: int) -> dict[str, Any]:
    """规则降级决策器：机械策略（等价现状——顺序执行未搜索 query，无则收敛）。"""
    pending = [q for q in queries if q not in executed]
    if pending:
        return {
            "action": "rewrite_query",
            "params": {"query": pending[0]},
            "reason": "规则降级：顺序执行未搜索 query",
        }
    return {
        "action": "converge",
        "params": {},
        "reason": "规则降级：无新 query 可执行",
    }


def decide(
    queries: list[str],
    executed: set[str],
    *,
    rounds: int,
    min_rounds: int,
    entries_count: int,
    target_entries: int,
    budget_left: int,
    card: dict[str, Any] | None = None,
    round_stats: list[dict[str, Any]] | None = None,
    llm_call: Callable[..., tuple[dict[str, Any], dict[str, Any]]],
    provider_id: str | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """decide 节点主入口。返回 (decision, meta)；meta 含 degraded/error 供 trace 记录。"""
    card = card or {}
    round_stats = round_stats or []
    ctx = build_user_context(card, round_stats, entries_count, target_entries, rounds, budget_left)
    meta: dict[str, Any] = {"degraded": False, "error": "", "llm_called": True}

    try:
        obj, _ = llm_call(DECIDE_SYSTEM, ctx, provider_id, model, max_tokens=800)
    except Exception as exc:  # noqa: BLE001  # LLM 失败 → 规则降级
        meta.update(degraded=True, error=f"LLM 调用失败: {exc}", llm_called=False)
        return rule_fallback_decision(queries, executed, rounds, min_rounds), meta

    ok, err = validate_decision(
        obj, rounds=rounds, min_rounds=min_rounds,
        entries_count=entries_count, target_entries=target_entries,
    )
    if not ok:
        meta.update(degraded=True, error=f"决策非法: {err}")
        return rule_fallback_decision(queries, executed, rounds, min_rounds), meta
    return obj, meta
