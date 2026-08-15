"""搜索规划：基于画像卡生成搜索 query 组合（≥3 条，覆盖 3 类来源）。"""
from __future__ import annotations

from typing import Any

from ..core.errors import AgentPlanError
from ..core.llm import llm
from ..core.providers import catalog
from .prompts import PLANNER_SYSTEM

SOURCE_TYPES = {"招聘平台", "官网", "社区"}

# 来源词归一化：LLM 可能输出变体词（企业官网/论坛/招聘网站…）
_SOURCE_NORM = {
    "企业官网": "官网", "官方": "官网", "官方网站": "官网", "官网地址": "官网",
    "社区论坛": "社区", "论坛": "社区", "知乎": "社区", "技术社区": "社区",
    "招聘网站": "招聘平台", "招聘网": "招聘平台", "招聘渠道": "招聘平台", "求职网站": "招聘平台",
}


def _norm_sources(sources: Any) -> list[str]:
    """归一化来源词，仅保留标准三类来源。"""
    if not isinstance(sources, list):
        return []
    out = []
    for s in sources:
        s = _SOURCE_NORM.get(str(s).strip(), str(s).strip())
        if s in SOURCE_TYPES and s not in out:
            out.append(s)
    return out


def build_queries(
    profile_card: dict[str, Any],
    provider_id: str | None = None,
    model: str | None = None,
    max_retry: int = 2,
) -> list[dict[str, Any]]:
    """返回 [{"q","sources":[...],"reason"}]。校验失败抛 AgentPlanError。"""
    city = profile_card.get("city", "")
    skills = "、".join(s["name"] for s in profile_card.get("skills", [])[:8])
    user = (
        f"画像卡：\n城市={city}\n技能={skills}\n"
        f"学历={profile_card.get('education')}，毕业={profile_card.get('grad_year')}\n"
        f"总结={profile_card.get('raw_summary','')}"
    )
    last_err = ""
    for _ in range(max_retry + 1):
        try:
            obj, _resp = llm.chat_json(PLANNER_SYSTEM, user, provider_id, model, max_tokens=1200)
            queries = obj.get("queries", [])
            if not isinstance(queries, list) or len(queries) < 3:
                last_err = "查询少于 3 条"
                continue
            # 来源词归一化后检查覆盖
            for q in queries:
                q["sources"] = _norm_sources(q.get("sources"))
            covered = {s for q in queries for s in q.get("sources", [])}
            missing = SOURCE_TYPES - covered
            # LLM 漏覆盖时程序自动补充缺失来源的查询（服务用户：不被输出质量卡死）
            if missing:
                last_err = ""
                base_q = str(queries[0].get("q", "")).strip()
                if not base_q and skills:
                    base_q = f"{skills} 岗位"
                for src in sorted(missing):
                    if not base_q:
                        continue
                    queries.append({"q": base_q, "sources": [src], "reason": f"自动补充「{src}」来源检索"})
            # 注入城市限定
            for q in queries:
                q["q"] = str(q.get("q", "")).strip()
                if city and city not in q["q"]:
                    q["q"] = f"{city} {q['q']}".strip()
            return queries
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
    raise AgentPlanError(f"搜索规划失败（重试 {max_retry} 次）: {last_err}")
