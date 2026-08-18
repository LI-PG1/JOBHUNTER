"""技能路由（契约 §4.2）：相关性三档校验 / 拓展。"""
from typing import List

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..core.errors import AppError, E_SKILL_BLOCK
from ..core.providers import LLMProvider
from ..engine.skills import extend_skills, validate_skills
from ..schemas import Job, Skill

router = APIRouter(prefix="/api/skills", tags=["skills"])


class ValidateBody(BaseModel):
    skills: List[Skill] = Field(min_length=1, max_length=30)
    jobs: List[Job] = Field(min_length=1, max_length=5)


class ExtendBody(BaseModel):
    skills: List[Skill] = Field(min_length=1, max_length=30)
    jobs: List[Job] = Field(min_length=1, max_length=5)
    skill_extend: bool = True


@router.post("/validate", response_model=dict)
async def validate(body: ValidateBody, request: Request):
    """技能相关性三档判定（§3.1.4）：pass/weak/block；block 时返回 40002（前端可拦截）。"""
    provider = LLMProvider(request.app.state.config, request.app.state.storage)
    rules = request.app.state.rules.skills_rules()
    result = await validate_skills(
        provider,
        [s.model_dump() for s in body.skills],
        [j.model_dump(by_alias=True) for j in body.jobs],
        rules,
    )
    if result["verdict"] == "block":
        raise AppError(E_SKILL_BLOCK, "技能与目标岗位相关性不足，请补充相关技能后重试", result)
    return {"code": 0, "message": "ok", "data": result}


@router.post("/extend", response_model=dict)
async def extend(body: ExtendBody, request: Request):
    """技能拓展：返回原技能 + 推荐技能合并列表。"""
    provider = LLMProvider(request.app.state.config, request.app.state.storage)
    recommended = await extend_skills(
        provider,
        [s.model_dump() for s in body.skills],
        [j.model_dump(by_alias=True) for j in body.jobs],
    )
    merged = [s.model_dump() for s in body.skills] + recommended
    return {"code": 0, "message": "ok", "data": {"skills": merged, "added": len(recommended)}}
