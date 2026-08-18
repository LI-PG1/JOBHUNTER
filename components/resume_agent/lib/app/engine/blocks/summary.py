"""自我评价生成（第一层，无 JD 依赖）：1~3 句 + 自估行数。"""
from typing import Optional

from ..prompts import summary_messages
from .base import GenContext, as_list, brief_of, llm_with_degrade, normalize_text_item


async def gen_summary(ctx: GenContext, *, review_feedback: Optional[str] = None) -> dict:
    industry = ctx.industry_rules
    messages = summary_messages(brief_of(ctx.resume), industry, ctx.factsheet,
                                review_feedback=review_feedback)
    parsed = await llm_with_degrade(
        ctx.provider, messages, max_tokens=4096, temperature=0.5,
        degrade={"sentences": []},
    )
    sentences = []
    # 用户已编辑句子（§5.5）不重写：保留原文并优先排前，剩余空位由 LLM 补充
    rest = 2
    for s in (ctx.resume.get("summary") or []):
        if not s.get("edited"):
            continue
        sentences.append({**normalize_text_item(s), "text": str(s.get("text", ""))[:300],
                          "edited": True, "criticality": "critical"})
        rest -= 1
    for s in as_list(parsed.get("sentences")):
        if rest <= 0:
            break
        text = str(s.get("text", "")).strip()
        if text:
            sentences.append({**normalize_text_item(s), "text": text[:300]})
            rest -= 1
    # 空降级兜底：至少保留 1 句（来自用户已有 summary）
    if not sentences and ctx.resume.get("summary"):
        sentences = [normalize_text_item({"text": s.get("text", "")})
                     for s in ctx.resume["summary"]][:2]
    return {"sentences": sentences[:2], "degraded": bool(parsed.get("degraded"))}
