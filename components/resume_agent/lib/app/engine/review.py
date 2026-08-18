"""审核回路（生成 → 规则审核 → 不合格带意见重写 → 复审）。

改造设计：《JL-Agent_改造设计.md》§2/§3；内容标准：《简历内容生成规范-resume_agent.md》§三。
- 规则审核：复用 `core.validation` 内容级规则审核 ⑧-⑪（逻辑链 / 密度均衡 / 数字口径）
  + 禁用词 / 占位符 + 数量约束（全部纯代码，零 LLM 成本）；
- blocker → 带审核意见调用**原板块生成函数**重写（复用编辑锁定合并，天然不覆盖用户已编辑内容）；
- 复审 ≤ `MAX_REWRITE_ROUNDS`（默认 1），仍不合格接受最优版本 `accept_with_issues`，整单继续 → done。
"""
import asyncio
import re
from typing import List, Optional

from ..core import validation as V
from ..schemas import BLOCK_WEIGHTS
from .blocks import BLOCK_GENERATORS
from .blocks.base import GenContext

# 审核范围：仅 LLM 生成的板块；education/skills/honor 纯规则板块不进入（改造设计 §2.4）
REVIEWABLE_BLOCKS = ("summary", "internship", "projects", "skill_extend")
# 每板块最多重写轮数默认值（config.review.max_rewrite_rounds 可覆盖，0~2）
MAX_REWRITE_ROUNDS = 1

# 占位符残留正则始终保留（结构兜底，无法用字面词表表达）；字面禁用词表来自 config.review.forbiddenWords
_PLACEHOLDER_PATTERN = re.compile(r"(待补充|TODO|xxx|XXX|\{\{.*?\}\})")


def _forbidden_patterns(cfg) -> list:
    """构建禁用词正则表：占位符兜底 + 配置词表（config.review.forbiddenWords，改造设计 §3.2 ③）。"""
    pats = [(_PLACEHOLDER_PATTERN, "占位符残留")]
    review_cfg = getattr(cfg, "review", None)
    for w in (review_cfg.forbidden_words if review_cfg else []) or []:
        w = str(w).strip()
        if not w:
            continue
        pats.append((re.compile(re.escape(w)), w))
    return pats


def _forbidden_hits(pats: list, text: str) -> List[str]:
    return [tag for pat, tag in pats if pat.search(text)]


def _issue(code: str, block: str, severity: str, message: str, index: int = 0, sub: Optional[int] = None) -> dict:
    item = {"code": code, "block": block, "severity": severity, "message": message, "index": index}
    if sub is not None:
        item["sub"] = sub
    return item


def check_rules(ctx: GenContext, block: str, output: dict) -> List[dict]:
    """规则审核（零 LLM）：内容级 ⑧⑩⑪（projects/internship）+ 禁用词 + 数量约束。

    降级（degraded/skipped）板块只接受不重写：返回空 issue（改造设计 §2.4）。
    """
    if not output or output.get("degraded") or output.get("skipped"):
        return []
    issues: List[dict] = []
    pats = _forbidden_patterns(ctx.config)

    if block == "projects":
        projects = output.get("projects") or []
        # 数量约束（⑤）：条数与 contentPlan 一致
        if ctx.project_count and len(projects) != ctx.project_count:
            issues.append(_issue("quantity", block, "blocker",
                                 f"项目条数 {len(projects)} != 计划 {ctx.project_count}"))
        for i, p in enumerate(projects):
            items = [(j, str(x.get("text") or ""), bool(x.get("edited")))
                     for j, x in enumerate(p.get("items") or [])]
            issues += V.check_star_chain(block, i, items)
            issues += V.check_density(block, i, items, V.ITEM_MIN_EFF)
            issues += V.check_metric_scope(block, i, items)
            for j, (_, text, edited) in enumerate(items):
                if edited:
                    continue
                for tag in _forbidden_hits(pats, text):
                    issues.append(_issue("forbidden", block, "blocker",
                                         f"命中「{tag}」（{text[:30]}…）", i, j))
    elif block == "internship":
        for i, it in enumerate(output.get("items") or []):
            duties = [(j, str(d.get("text") or ""), bool(d.get("edited")))
                      for j, d in enumerate(it.get("duties") or [])]
            issues += V.check_density(block, i, duties, V.DUTY_MIN_EFF)
            issues += V.check_metric_scope(block, i, duties)
            for j, (_, text, edited) in enumerate(duties):
                if edited:
                    continue
                for tag in _forbidden_hits(pats, text):
                    issues.append(_issue("forbidden", block, "blocker",
                                         f"命中「{tag}」（{text[:30]}…）", i, j))
    elif block == "summary":
        sentences = output.get("sentences") or []
        texts = [(j, str(s.get("text") or ""), bool(s.get("edited")))
                 for j, s in enumerate(sentences)]
        if not texts:
            issues.append(_issue("quantity", block, "blocker", "自我评价为空"))
        for j, (_, text, edited) in enumerate(texts):
            if edited:
                continue
            for tag in _forbidden_hits(pats, text):
                issues.append(_issue("forbidden", block, "blocker",
                                     f"命中「{tag}」（{text[:30]}…）", 0, j))
    elif block == "skill_extend":
        skills = output.get("skills") or []
        cats = {str(s.get("category") or "") for s in skills}
        if not 3 <= len(cats) <= 5:
            issues.append(_issue("quantity", block, "blocker",
                                 f"技能分类数 {len(cats)} 超出 3~5"))
    return issues


def rewrite_feedback_text(block: str, issues: List[dict]) -> str:
    """把审核意见格式化为重写反馈（追加到原板块 user 消息末尾，prompts 层约定）。"""
    lines = [f"- [{x.get('severity')}] {x.get('message')}" for x in issues]
    return (
        "【上轮审核意见（必须逐条响应修正）】\n"
        + "\n".join(lines)
        + "\n【硬约束】不改变公司/职位/时间等事实；保留用户已编辑条目原文；"
          "维持数量约束（bullet_limit / project_count）；不要引入新问题。"
    )


def _blockers(issues: List[dict]) -> List[dict]:
    return [x for x in issues if x.get("severity") == "blocker"]


def _max_rounds(ctx: GenContext) -> int:
    """从 config.review.max_rewrite_rounds 读取重写轮数（0~2），缺失回退默认。"""
    review_cfg = getattr(ctx.config, "review", None)
    if review_cfg is None:
        return MAX_REWRITE_ROUNDS
    try:
        return max(0, min(2, int(review_cfg.max_rewrite_rounds)))
    except (TypeError, ValueError):
        return MAX_REWRITE_ROUNDS


async def review_block(ctx: GenContext, block: str) -> dict:
    """单板块审核回路：规则审核 → 有 blocker → 带意见重写 → 复审（≤MAX_REWRITE_ROUNDS）。

    重写走原板块生成函数（`BLOCK_GENERATORS[block](ctx, review_feedback=...)`），
    复用其编辑锁定合并与数量约束；复审未改善 → 回退最优版本。
    """
    output = ctx.blocks.get(block) or {}
    issues = check_rules(ctx, block, output)
    rounds = 0
    rewritten = False
    max_rounds = _max_rounds(ctx)

    while _blockers(issues) and rounds < max_rounds:
        rounds += 1
        try:
            new_output = await BLOCK_GENERATORS[block](ctx, review_feedback=rewrite_feedback_text(block, issues))
        except Exception:   # 重写失败 → 保留原输出，接受现状
            break
        rewritten = True
        new_issues = check_rules(ctx, block, new_output)
        # 复审未改善（blocker 未减少）→ 回退最优版本
        if len(_blockers(new_issues)) >= len(_blockers(issues)):
            break
        ctx.blocks[block] = new_output
        output, issues = new_output, new_issues

    blockers = _blockers(issues)
    return {
        "block": block,
        "verdict": "pass" if not blockers else "accept_with_issues",
        "issues": issues,
        "rounds": rounds,
        "rewritten": rewritten,
        "blockerCount": len(blockers),
    }


async def run_review(runner, ctx: GenContext) -> None:
    """reviewing 阶段编排：并行审核 4 个 LLM 板块，blocker 触发重写，推进度 + 推送 block.review。

    config.review.enabled=false 时整阶段跳过（不推事件、不占进度）。
    """
    review_cfg = getattr(ctx.config, "review", None)
    if review_cfg is not None and not review_cfg.enabled:
        return
    await runner._set_stage(ctx.task_id, "reviewing", 2)
    blocks = [b for b in REVIEWABLE_BLOCKS if ctx.blocks.get(b)]
    results = await asyncio.gather(*[review_block(ctx, b) for b in blocks]) if blocks else []

    ctx.review_summary = {"results": results}
    for r in results:
        await runner._push(ctx.task_id, "block.review", {
            "taskId": ctx.task_id,
            "block": r["block"],
            "rounds": r["rounds"],
            "verdict": r["verdict"],
            "blockerCount": r["blockerCount"],
            "rewritten": r["rewritten"],
        })
    if results and not runner._canceled(ctx.task_id):
        total = sum(runner._relevant_weights(ctx).values()) + BLOCK_WEIGHTS["review"]
        runner._add_progress(ctx.task_id, BLOCK_WEIGHTS["review"] / total)
