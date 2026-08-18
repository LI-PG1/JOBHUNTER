"""教育排版（第一层，固定）：按结束时间倒序，规范化输出。"""
from .base import GenContext


def _month_key(value: str) -> tuple:
    if not value or "." not in value:
        return (0, 0)
    y, m = value.split(".", 1)
    try:
        return int(y), int(m)
    except ValueError:
        return (0, 0)


async def gen_education(ctx: GenContext) -> dict:
    items = sorted(
        (ctx.resume.get("education") or []),
        key=lambda e: _month_key(e.get("endMonth", "")),
        reverse=True,
    )
    return {"items": items}


def _category_order(category: str) -> int:
    return {"专业技能": 0, "工具与框架": 1, "语言能力": 2}.get(category, 9)


async def gen_skills(ctx: GenContext) -> dict:
    """技能分类优化（第一层）：去重 + 按类别排序（不调 LLM）。"""
    seen, ordered = set(), []
    for s in ctx.resume.get("skill") or []:
        name = str(s.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(s)
    ordered.sort(key=lambda s: _category_order(s.get("category", "")))
    return {"skills": ordered}


async def gen_honor(ctx: GenContext) -> dict:
    """荣誉（非常驻）：有则保留原值（格式化时间），空 → 整块跳过（skipped）。"""
    items = [h for h in (ctx.resume.get("honor") or []) if str(h.get("name", "")).strip()]
    if not items:
        return {"skipped": True, "items": []}
    return {"items": items}
