"""N4 洗涤去重（scrub）。

对齐原 app/plugins/scrub.py：normalize（字段清洗）+ dedupe（title+company 去重）
+ is_job 初判（P0 简化：URL/标题含岗位信号词）。
"""
from __future__ import annotations

import re
from typing import Any

from match_agent.state import MatchState

_JOB_HINT = re.compile(
    r"(job|career|jobs|zhaopin|boss|liepin|lagou|51job|招聘|岗位|职位|实习)", re.I
)


def _normalize(title: str, company: str) -> tuple[str, str]:
    title = re.sub(r"\s+", " ", (title or "")).strip()
    company = re.sub(r"[·\-—]", " ", (company or "")).strip()
    return title, company


def _extract_company(raw: dict[str, Any]) -> str:
    """从原始条目提取公司名（P0 简化：snippet 无公司则留空）。"""
    return raw.get("company") or ""


def scrub(state: MatchState) -> MatchState:
    """原始条目 → 归一化 + 去重 + is_job 初判 → entries。

    增量更新：entries。
    """
    raw_items = state.get("_raw_items") or []
    seen: set[tuple[str, str]] = set()
    entries: list[dict[str, Any]] = []
    for raw in raw_items:
        title, _ = _normalize(raw.get("title", ""), _extract_company(raw))
        company = _extract_company(raw)
        key = (title.lower(), company.lower())
        if not title or key in seen:
            continue
        seen.add(key)
        entries.append({
            "title": title,
            "company": company,
            "url": raw.get("url", ""),
            "snippet": (raw.get("snippet") or "")[:120],
            "date": raw.get("date", ""),
            "is_job": bool(_JOB_HINT.search(title) or _JOB_HINT.search(raw.get("url", ""))),
            "query": raw.get("query", ""),
            "backend": raw.get("backend", ""),
        })
    return {**state, "entries": entries}
