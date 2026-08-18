"""N10 保存（save · P0 契约层）。

对齐原 loop.py 行 353-357（落盘 md/html 到 output/）：
- P0 作为库组件，落盘由调用方决定；本节点负责把 final_list 组装为**输出契约**
  （§6.1）：{match_results, gap_summary, llm_verdicts, errors}。
- gap_summary（Q7）：由 match_agent 聚合 missing_skills / reject_reasons / search_health，
  供大脑 N5 汇入 gate 判定、N7 差距分析消费（区分「没搜到 vs 搜到了但不匹配」）。
- P0 不写文件系统（真实落盘在 M2 大脑接入时由大脑侧或 save 配置决定）。
"""
from __future__ import annotations

from collections import Counter

from match_agent.state import MatchState


def _aggregate_gap_summary(state: MatchState) -> dict:
    """从 entries（scrub 后）+ judged（判定后）聚合结构化差距摘要（Q7）。

    - missing_skills：accepted/gap 岗位共有的画像技能缺口（按频次 top5）
    - reject_reasons：excluded 岗位被拒原因分布（按频次 top5）
    - search_health：搜索覆盖健康度（entries_raw 低→「没搜到」；missing 大→「不匹配」）
    """
    entries = state.get("entries") or []
    judged = state.get("judged") or []
    missing_counter: Counter[str] = Counter()
    reject_counter: Counter[str] = Counter()
    status_count = {"accepted": 0, "gap": 0, "excluded": 0}
    for j in judged:
        status = j.get("status", "excluded")
        status_count[status] = status_count.get(status, 0) + 1
        if status in ("accepted", "gap"):
            for s in j.get("missing_skills") or []:
                missing_counter[s] += 1
        if status == "excluded":
            for r in j.get("reasons") or []:
                reject_counter[r] += 1
    return {
        "missing_skills": [
            {"skill": s, "count": c} for s, c in missing_counter.most_common(5)
        ],
        "reject_reasons": [
            {"reason": r, "count": c} for r, c in reject_counter.most_common(5)
        ],
        "search_health": {
            "entries_raw": len(entries),
            "accepted": status_count["accepted"],
            "gap": status_count["gap"],
            "excluded": status_count["excluded"],
        },
    }


def save(state: MatchState) -> MatchState:
    """final_list → match_results 契约 + gap_summary（Q7）。"""
    return {
        **state,
        "match_results": list(state.get("final_list") or []),
        "gap_summary": _aggregate_gap_summary(state),
        "llm_verdicts": [],                     # P1 混合判定后填充
    }
