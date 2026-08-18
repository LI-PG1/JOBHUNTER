"""项目生成（第二层，依赖共享事实表）：种子润色 + 空位按骨架创作。

- 种子：用户已有项目按 techStack 与 coreSkills 相关度取前 projectCount 条。
- 空位：按方向骨架（rules/projects/mapping.json）创作（source=ai-created）。
"""
from typing import Optional

from ..prompts import projects_messages
from .base import GenContext, as_list, llm_with_degrade, normalize_text_item


def _pick_seeds(ctx: GenContext) -> list:
    """按技术栈与 JD 核心技能匹配度挑选种子项目（保留用户输入优先）。"""
    user_projects = [p for p in (ctx.resume.get("project") or [])
                     if str(p.get("name", "")).strip()]
    if not user_projects:
        return []
    core = set(ctx.factsheet.get("coreSkills") or [])

    def score(p: dict) -> int:
        pool = " ".join([p.get("name", "")] + list(p.get("techStack") or [])).lower()
        return sum(1 for k in core if k and k.lower() in pool)

    ranked = sorted(user_projects, key=score, reverse=True)
    return ranked[: ctx.project_count]


def _skeleton(ctx: GenContext) -> str:
    mapping = ctx.rules.projects_mapping() if ctx.rules else {}
    direction = ctx.factsheet.get("direction", "")
    for d in mapping.get("direction_projects") or []:
        if d.get("direction") == direction or (direction and direction in d.get("direction", "")):
            return ", ".join(d.get("skeletons") or [])
    return ""


def bullet_limit(page_option: str, project_count: int) -> int:
    """每项目要点数（STAR 四段固定 4 条；两页项目少时放宽行动条数）。"""
    if page_option == "one-page":
        return 4                                   # 一页 → S/T/A/R 四段各 1 条（定稿 A，2026-08-17）
    return 6 if project_count <= 2 else 4          # 两页：项目≤2 → 6 条；≥3 → STAR 四段 4 条


async def gen_projects(ctx: GenContext, *, review_feedback: Optional[str] = None) -> dict:
    count = ctx.project_count
    if count <= 0:
        return {"projects": [], "skipped": True}
    if not ctx.factsheet:
        return {"projects": [], "degraded": True}

    seeds = _pick_seeds(ctx)
    # 用户已编辑要点（§5.5）不重写：按项目名匹配保留原文
    edited_by_name = {
        str(p.get("name", "")).strip(): [i for i in (p.get("items") or []) if i.get("edited")]
        for p in (ctx.resume.get("project") or [])
    }
    # 种子数量不足以填满 → 需要创作空位
    skeleton = _skeleton(ctx) if len(seeds) < count else ""
    limit = bullet_limit(ctx.page_option, count)
    messages = projects_messages(
        seeds, skeleton, ctx.factsheet, ctx.industry_rules, count, limit, ctx.search_results,
        review_feedback=review_feedback,
    )
    parsed = await llm_with_degrade(
        ctx.provider, messages, max_tokens=8192, temperature=0.4,
        degrade={"projects": []},
    )
    projects = []
    for p in as_list(parsed.get("projects")):
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        items = []
        seen = set()
        for i in edited_by_name.get(name, []):
            text = str(i.get("text", "")).strip()
            if not text:
                continue
            items.append({**normalize_text_item(i), "text": text[:500],
                          "edited": True, "criticality": "critical"})
            seen.add(text)
        for i in as_list(p.get("items")):
            text = str(i.get("text", "")).strip()
            if text and text not in seen:
                items.append(normalize_text_item(i))
                seen.add(text)
        # 数量约束：按项目数动态（一页 ≤4 / 两页 ≤6，项目多时压缩）
        items = items[:limit] or [normalize_text_item({"text": "（待补充）"})]
        projects.append({
            "name": name[:64],
            "role": str(p.get("role") or "开发")[:32],
            "startMonth": str(p.get("startMonth") or "")[:7],
            "endMonth": str(p.get("endMonth") or "")[:7],
            "techStack": [str(t)[:40] for t in (p.get("techStack") or [])][:8],
            "items": items,
            "source": "polished" if p.get("source") == "polished" and seeds else "ai-created",
            "aiFlag": True,
        })
    # 兜底：LLM 产出不足 → 补足种子
    if len(projects) < count and seeds:
        for seed in seeds:
            if len(projects) >= count:
                break
            projects.append({
                "name": seed.get("name", ""), "role": seed.get("role", "开发"),
                "startMonth": seed.get("startMonth", ""), "endMonth": seed.get("endMonth", ""),
                "techStack": list(seed.get("techStack") or []),
                "items": [({**normalize_text_item(i), "text": str(i.get("text", ""))[:500],
                            "edited": True, "criticality": "critical"}
                           if i.get("edited") else normalize_text_item(i))
                          for i in (seed.get("items") or [])] or [normalize_text_item({"text": "（待补充）"})],
                "source": "user-input", "aiFlag": False,
            })
    return {"projects": projects[:count], "degraded": bool(parsed.get("degraded"))}
