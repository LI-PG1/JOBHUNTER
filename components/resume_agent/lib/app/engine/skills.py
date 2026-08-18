"""技能相关性校验与拓展（契约 §3.1.4 / §4.2）。

三档判定（skills/rules.json）：score ≥ pass_threshold(0.6) → pass；
weak_threshold(0.3)~0.6 → weak；<0.3 → block。
关键词兜底（keyword_fallback=true）：技能名直接命中 JD 文本时，
即使 LLM 低分也兜底到 pass 档（满足 E3「<0.3 阻止 + 关键词兜底」）。
"""
import json
from typing import List

from ..core.errors import AppError, E_LLM
from ..core.providers import LLMProvider
from .analysis import clamp_score, extract_json
from .prompts import skill_extend_messages, skill_validate_messages


async def validate_skills(
    provider: LLMProvider,
    skills: List[dict],
    jobs: List[dict],
    skills_rules: dict,
) -> dict:
    """技能相关性三档校验 → {score, verdict: pass|weak|block, reason}。"""
    threshold_pass = float(skills_rules.get("pass_threshold", 0.6))
    threshold_weak = float(skills_rules.get("weak_threshold", 0.3))
    keyword_fallback = bool(skills_rules.get("keyword_fallback", True))

    names = [str(s.get("name", "")).strip() for s in skills if str(s.get("name", "")).strip()]
    jd_text = " ".join(f"{j.get('title', '')} {(j.get('jdText') or '').strip()}" for j in jobs).lower()
    hits = [n for n in names if n.lower() in jd_text]

    content = await provider.chat(
        skill_validate_messages(skills, jobs, skills_rules),
        json_mode=True,
        max_tokens=1024,
        temperature=0.2,
    )
    parsed = extract_json(content)
    llm_score = clamp_score(parsed.get("score"))
    reason = str(parsed.get("reason") or "").strip() or "基于技能与岗位相关度评估"

    # 关键词兜底：技能名直接命中 JD → 按契约放行到 pass 档
    score = llm_score
    if keyword_fallback and hits:
        score = max(score, threshold_pass)
        reason = f"技能「{'、'.join(hits[:3])}」直接命中岗位关键词，{reason}"

    verdict = "pass" if score >= threshold_pass else ("weak" if score >= threshold_weak else "block")
    return {"score": round(score, 2), "verdict": verdict, "reason": reason}


async def extend_skills(provider: LLMProvider, skills: List[dict], jobs: List[dict]) -> List[dict]:
    """技能拓展：LLM 基于 JD 推荐 3~6 个补充技能。"""
    content = await provider.chat(
        skill_extend_messages(skills, jobs),
        json_mode=True,
        max_tokens=4096,
        temperature=0.4,
    )
    parsed = extract_json(content)
    recommended = parsed.get("recommended")
    if not isinstance(recommended, list):
        raise AppError(E_LLM, "技能拓展结果结构非法")
    return [
        {
            "category": str(r.get("category", "专业技能"))[:16],
            "name": str(r.get("name", "")).strip()[:64],
            "level": str(r.get("level", "熟悉"))[:8],
        }
        for r in recommended
        if str(r.get("name", "")).strip()
    ]
