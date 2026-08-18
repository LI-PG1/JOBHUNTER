"""/api/match —— 岗位匹配（直连 LLM，AI 推荐岗位）。

单仓库「点击即用」版：不再转发外部 JS-Agent（搜索真实在招岗位需商业数据源），
改为直连 LLM 基于求职者画像生成「AI 推荐岗位」清单并评估匹配度，
岗位来源标注为 `source: "AI 推荐"`（示意/参考，非实时在招）。

- POST /api/match   生成推荐岗位（同步返回）
- GET  /api/match/{job_id}  返回最近一次结果（兼容旧轮询前端）
"""
import time
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from clients.llm import LLMKeyError, chat_json

router = APIRouter()

_MATCH_SYSTEM = (
    "你是资深求职顾问。根据求职者画像，为其推荐与画像匹配、且有求职价值的岗位。\n"
    "要求：岗位与画像技能/方向匹配度合理（80+ 为强匹配），岗位信息为行业常见代表性岗位（示意参考）；"
    "link 为该岗位的招聘/公司主页链接（优先真实可访问地址，无法确认时给出公司招聘主页，不要编造具体职位页）。\n"
    "只输出严格 JSON，不要多余文字，格式：\n"
    '{"jobs": [{"title": "岗位名", "company": "公司名", "city": "城市", "salary": "薪资", '
    '"industry": "行业", "skills": ["技能要求"], "match_score": 0~100 整数, '
    '"link": "岗位/公司招聘链接", '
    '"match_reason": ["匹配理由"], "education": "学历要求", "experience": "经验要求", '
    '"source": "AI 推荐"}]}'
)

# 最近一次生成结果（job_id → 结果），供 GET /api/match/{job_id} 兼容返回
_LATEST: Dict[str, Dict[str, Any]] = {}


def _llm_recommend(req: Dict[str, Any]) -> List[Dict[str, Any]]:
    profile_text = str(req.get("profile_text") or "").strip()
    city = str(req.get("city") or "").strip()
    max_results = max(1, min(int(req.get("max_results") or 5), 20))
    user = (
        f"求职者画像：\n{profile_text or '（未提供）'}\n\n"
        f"期望城市：{city or '不限'}\n\n"
        f"请推荐 {max_results} 个岗位并输出 JSON："
    )
    data = chat_json(_MATCH_SYSTEM, user)
    jobs = data.get("jobs") or []
    if not isinstance(jobs, list):
        raise HTTPException(status_code=502, detail="AI 返回的岗位清单格式异常")
    for j in jobs:
        if not isinstance(j, dict):
            continue
        j.setdefault("source", "AI 推荐")
        j.setdefault("link", "")
        j.setdefault("city", city or j.get("city") or "不限")
        for key in ("skills", "match_reason", "reasons"):
            v = j.get(key)
            if isinstance(v, str):
                j[key] = [v] if v else []
        try:
            j["match_score"] = max(0, min(100, int(float(j.get("match_score") or 0))))
        except (TypeError, ValueError):
            j["match_score"] = 0
    return jobs


@router.post("/match")
def start_match(req: Dict[str, Any]) -> Dict[str, Any]:
    """生成 AI 推荐岗位（同步返回，无需轮询）。"""
    try:
        jobs = _llm_recommend(req)
    except LLMKeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    job_id = "llm-" + str(int(time.time() * 1000)) + "-" + uuid.uuid4().hex[:6]
    payload = {"status": "done", "job_id": job_id, "jobs": jobs, "channel": "AI 推荐"}
    _LATEST[job_id] = payload
    return payload


@router.get("/match/{job_id}")
def get_match(job_id: str) -> Dict[str, Any]:
    """返回对应 job_id 的结果（兼容旧轮询前端；同步接口基本走不到）。"""
    if job_id in _LATEST:
        return _LATEST[job_id]
    raise HTTPException(status_code=404, detail="匹配结果不存在或已过期")
