"""匹配 API：启动 Agent 任务 / 查询进度 / 取消。"""
from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from ..agent.loop import runner, tasks
from ..config import key_store
from ..core.errors import JSAgentError

router = APIRouter(prefix="/api/match", tags=["match"])

# job_id → 取消事件
_abort_events: dict[str, threading.Event] = {}
_abort_lock = threading.Lock()


def _abort_event(job_id: str) -> threading.Event:
    with _abort_lock:
        ev = _abort_events.get(job_id)
        if ev is None:
            ev = threading.Event()
            _abort_events[job_id] = ev
        return ev


@router.post("")
async def start_match(req: dict[str, Any]) -> dict[str, Any]:
    """启动匹配任务，返回 job_id。"""
    profile_text = str(req.get("profile_text", "")).strip()
    if len(profile_text) < 20:
        raise HTTPException(status_code=400, detail="画像信息过短，请补充学历/技能/项目/实习经历等（至少 20 字）")
    city = str(req.get("city", "")).strip()
    if not city:
        raise HTTPException(status_code=400, detail="请选择意向城市")
    max_results = int(req.get("max_results") or 20)
    if max_results not in (10, 20, 30, 40, 50, 100):
        raise HTTPException(status_code=400, detail="条数必须是 10/20/30/40/50/100")

    # Key 预检（快速失败，避免异步任务空转）：指定厂商 → 检查该厂商；未指定 → 检查任一厂商
    keys = key_store.load()
    pid = str(req.get("provider_id") or "")
    if pid:
        entry = keys.get(pid)
        if not entry or not entry.get("api_key"):
            raise HTTPException(status_code=400, detail=f"厂商 {pid} 未配置 API Key，请先到控制台配置")
    elif not any(k.get("api_key") for k in keys.values()):
        raise HTTPException(status_code=400, detail="未配置任何大模型 API Key，请先到控制台配置")

    job_id = uuid.uuid4().hex[:12]
    tasks.create(job_id)
    ev = _abort_event(job_id)
    ev.clear()
    request = {
        "profile_text": profile_text,
        "city": city,
        "max_results": max_results,
        # 前端多选透传；空列表 = 不限（企业类型过滤在 loop 内完成，前端已默认勾选全部）
        "company_types": req.get("company_types") or [],
        "experience_years": req.get("experience_years"),
        "provider_id": req.get("provider_id"),
        "model": req.get("model"),
        # M1 改造可选参数（改造设计 §5.1）：mode=scout|match；judge_llm/search_agent=false 时回退确定性行为
        "mode": req.get("mode"),
        "judge_llm": req.get("judge_llm"),
        "search_agent": req.get("search_agent"),
    }

    def _worker() -> None:
        try:
            result = runner.run(request, lambda p, m: tasks.update(job_id, p, m), ev)
            tasks.done(job_id, result)
        except JSAgentError as exc:
            tasks.fail(job_id, exc.message)
        except Exception as exc:  # noqa: BLE001
            tasks.fail(job_id, f"内部错误: {exc}")
        finally:
            with _abort_lock:
                _abort_events.pop(job_id, None)

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id, "status": "running"}


@router.get("/{job_id}")
async def get_match(job_id: str) -> dict[str, Any]:
    state = tasks.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return state


@router.get("/{job_id}/trace")
async def get_match_trace(job_id: str) -> dict[str, Any]:
    """搜索轨迹审计（改造设计 §5.1）：决策历史 + 收敛原因 + 判定统计。"""
    state = tasks.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    result = state.get("result") or {}
    return {
        "status": state.get("status"),
        "trace": result.get("_trace") or {"history": [], "converge_reason": "", "llm_calls": 0, "rounds": 0},
        "debug": result.get("_debug") or {},
    }


@router.delete("/{job_id}")
async def cancel_match(job_id: str) -> dict[str, Any]:
    state = tasks.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    ev = _abort_event(job_id)
    ev.set()
    tasks.cancel(job_id)
    return {"ok": True, "status": "cancelling"}
