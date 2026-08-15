"""技能拓展（第二层，skillExtend=true 时）：基于 JD 推荐补充技能（LLM 重试 + 降级）。

补充技能按「有机分类」返回，但 LLM 易产出碎分类（如单技能各占一类）。
本块做分类收敛：分类 3~5 个、单技能非固定分类并入相近大类、语言能力独立保留。
"""
from ..prompts import skill_extend_messages
from .base import GenContext, llm_with_degrade

# 固定分类（模板默认顺序，始终独立成行）：专业技能/工具与框架/语言能力
_FIXED_CATS = ("专业技能", "工具与框架", "语言能力")
# 碎分类并入规则：编程语言类并入专业技能，其余单技能并入工具与框架
_CAT_MERGE = {
    "编程语言": "专业技能", "程序语言": "专业技能", "编程": "专业技能",
}


def _coalesce_categories(fresh: list) -> list:
    """分类收敛：≤5 类、每类 ≥1（单技能非固定分类并入相近大类，不独立占行）。"""
    if not fresh:
        return fresh
    groups: dict[str, list] = {}
    for s in fresh:
        cat = str(s.get("category") or "专业技能")[:16]
        groups.setdefault(cat, []).append(s)
    # 1) 单技能的非固定分类并入相近大类（语言能力例外：带等级独立保留）
    for cat, items in list(groups.items()):
        if len(items) == 1 and cat not in _FIXED_CATS:
            target = _CAT_MERGE.get(cat, "工具与框架")
            groups.setdefault(target, []).extend({**s, "category": target} for s in items)
            del groups[cat]
    # 2) 分类数 >5：保留固定 3 类 + 技能数最多的额外类（共 ≤5），其余并入专业技能
    if len(groups) > 5:
        extra = [(c, len(v)) for c, v in groups.items() if c not in _FIXED_CATS]
        extra.sort(key=lambda x: x[1], reverse=True)
        keep = {c for c, _ in extra[: max(0, 5 - len(_FIXED_CATS))]}
        for cat, items in list(groups.items()):
            if cat in keep:
                continue
            groups.setdefault("专业技能", []).extend(
                {**s, "category": "专业技能"} for s in items)
            del groups[cat]
    out: list[dict] = []
    for items in groups.values():
        out.extend(items)
    return out


async def gen_skill_extend(ctx: GenContext) -> dict:
    if not ctx.skill_extend_enabled:
        return {"skills": [], "skipped": True}
    parsed = await llm_with_degrade(
        ctx.provider,
        skill_extend_messages(ctx.resume.get("skill") or [], ctx.jobs),
        max_tokens=4096, temperature=0.4,
        degrade={"recommended": []},
    )
    recommended = parsed.get("recommended")
    if not isinstance(recommended, list):
        return {"skills": [], "degraded": True, "error": "技能拓展结果结构非法"}
    existing = {str(s.get("name", "")).strip() for s in (ctx.resume.get("skill") or [])}
    fresh = []
    for r in recommended:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "").strip()[:64]
        if not name or name in existing:
            continue
        fresh.append({
            "category": str(r.get("category") or "专业技能")[:16],
            "name": name,
            "level": str(r.get("level") or "熟悉")[:8],
        })
        existing.add(name)
    return {"skills": _coalesce_categories(fresh), "degraded": bool(parsed.get("degraded"))}
