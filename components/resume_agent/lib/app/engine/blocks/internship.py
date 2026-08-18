"""实习美化（第一层，有则做）：仅优化措辞补量化，不创造事实。"""
from typing import Optional

from ..prompts import internship_messages
from .base import GenContext, as_list, llm_with_degrade, normalize_text_item


def _degrade_internships(internships: list, limit: int) -> list:
    """降级兜底：以用户原文为唯一事实，仅做结构补齐，不虚构内容。

    与 LLM 正常输出对齐的高密度结构：overview（主要职责概述）+ 主题化条目。
    - overview：优先取用户已填；未填且职责 ≥2 条时，取首条职责作概述，其余作条目；
    - duties：保留用户原文（不得虚构量化），已编辑职责保持 critical。
    """
    items = []
    for it in internships:
        raw, seen = [], set()
        for d in (it.get("duties") or []):
            text = str(d.get("text", "")).strip()[:300]
            if not text or text in seen:
                continue
            seen.add(text)
            raw.append({**normalize_text_item(d), "text": text})
        overview = str(it.get("overview") or "").strip()[:200]
        if not overview and len(raw) >= 2:
            overview = raw[0]["text"]   # 取首条职责作「主要职责」概述，其余作条目
            raw = raw[1:]
        items.append({
            "company": it.get("company", ""),
            "position": it.get("position", ""),
            "startMonth": it.get("startMonth", ""),
            "endMonth": it.get("endMonth", ""),
            "overview": overview,
            "duties": (raw or [normalize_text_item({"text": "（待补充）"})])[:limit],
        })
    return items


async def gen_internship(ctx: GenContext, *, review_feedback: Optional[str] = None) -> dict:
    internships = ctx.resume.get("internship") or []
    if not internships:
        return {"items": [], "skipped": True}

    limit = 3 if ctx.page_option == "one-page" else 4   # 主要工作内容条数（按页数裁剪）
    messages = internship_messages(internships, ctx.industry_rules, review_feedback=review_feedback)
    parsed = await llm_with_degrade(
        ctx.provider, messages, max_tokens=4096, temperature=0.4,
        # 失败降级：对用户原文做结构补齐（概述 + 保留职责），不直接回退原文
        degrade={"items": _degrade_internships(internships, limit)},
    )
    items = []
    src_by_company = {i.get("company", ""): i for i in internships}
    for it in as_list(parsed.get("items")):
        src = src_by_company.get(it.get("company", ""), {})
        duties = []
        # 用户已编辑职责（§5.5）不重写：按来源公司保留原文，其余由 LLM 补充
        seen = set()
        for d in (src.get("duties") or []):
            if not d.get("edited"):
                continue
            text = str(d.get("text", "")).strip()
            if not text:
                continue
            duties.append({**normalize_text_item(d), "text": text[:300],
                           "edited": True, "criticality": "critical"})
            seen.add(text)
        for d in as_list(it.get("duties")):
            text = str(d.get("text", "")).strip()
            if text and text not in seen:
                duties.append({**normalize_text_item(d), "text": text[:300]})
                seen.add(text)
        # 公司/职位/时间以用户原值为准，LLM 输出仅作措辞参考
        items.append({
            "company": src.get("company", it.get("company", "")),
            "position": src.get("position", it.get("position", "")),
            "startMonth": src.get("startMonth", it.get("startMonth", "")),
            "endMonth": src.get("endMonth", it.get("endMonth", "")),
            "overview": str(src.get("overview") or it.get("overview") or "").strip()[:200],
            "duties": (duties or [normalize_text_item({"text": "（待补充）"})])[:limit],
        })
    return {"items": items, "degraded": bool(parsed.get("degraded"))}
