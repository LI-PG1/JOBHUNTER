"""web/routers/run.py —— 大脑全流程封装（HITL 生命周期版，同步）。

对比 v0.1 同步 invoke 版：新版图含 interrupt（N2 画像追问 / N9 投递确认），
故增加「发起 → 遇 interrupt 返回前端 → 用户答复 resume 继续」的会话模型：

- POST /api/run           发起：invoke 一步；遇 interrupt 返回给前端；否则返回聚合结果
- POST /api/run/resume    继续：Command(resume=用户答复) 再走一步
- 返回统一为 {thread_id, status: "done"|"interrupt", data?|interrupts?}

每个请求独立 thread_id（进程内 MemorySaver 检查点）；全流程在进程内
build_graph().compile() 上执行（Q9 进程内组件调用），同旧版契约。
"""
import threading
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from graph.build import build_graph

router = APIRouter()

# 进程内编译图 + 内存检查点（thread_id 隔离；锁串行化执行，mock 级延迟无感）
_memory = MemorySaver()
_graph = build_graph().compile(checkpointer=_memory)
_LOCK = threading.Lock()


class ProfileIn(BaseModel):
    """结构化画像（与 JobHunterState.profile 对齐，前端表单组装）。
    字段与前端 collectProfile() 对齐；教育/实习/联系方式等缺失会直接导致
    简历组件信息不全（名称占位、教育/实习空），故全量透传。"""
    name: str = "求职者"
    email: str = ""
    phone: str = ""
    website: str = ""
    awards: List[str] = []
    education: List[Dict[str, Any]] = []
    internships: List[Dict[str, Any]] = []
    skills: List[str] = []
    experience: List[Dict[str, Any]] = []
    preference: Dict[str, Any] = Field(default_factory=dict)


class JobIn(BaseModel):
    title: str
    jd: str = ""
    company: str = ""


class RunRequest(BaseModel):
    profile: Optional[ProfileIn] = None
    target_jobs: List[JobIn] = []
    user_goal: str = "帮我找工作"
    submission_input: Dict[str, Any] = Field(default_factory=dict)
    config: Dict[str, Any] = Field(default_factory=dict)  # 如 {"skip_confirm": true}


class ResumeRequest(BaseModel):
    thread_id: str
    resume: Dict[str, Any]  # N2: {"城市": "深圳", ...} 补充字段；N9: {"action": "approve"|"modify"|"reject", ...}


def _aggregate(state: Dict[str, Any]) -> Dict[str, Any]:
    """最终 state → 前端聚合视图（只取可渲染字段，剔除内部冗余）。"""
    return {
        "resume": state.get("resume"),
        "resume_round": state.get("resume_round"),
        "match_results": state.get("match_results", []),
        "match_gap": state.get("match_gap", {}),
        "gate_verdict": state.get("gate_verdict"),
        "gap_summary": state.get("gap_summary", {}),
        "resume_feedback": state.get("resume_feedback", []),
        "interview_materials": state.get("interview_materials", {}),
        "report": state.get("report", {}),
        "n7_stats": state.get("n7_stats", {}),
        "errors": state.get("errors", []),
        "submission_plan": state.get("submission_plan", {}),      # Q10 投递清单
        "submission_input": state.get("submission_input", {}),
        "missing_fields": state.get("missing_fields", []),
        "profile": state.get("profile", {}),
        "user_goal": state.get("user_goal", ""),
    }


def _step(thread_id: str, payload: Optional[Dict[str, Any]],
          resume: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """执行一步（invoke 或 resume），统一为 done / interrupt 两种返回。"""
    config = {"configurable": {"thread_id": thread_id}}
    with _LOCK:
        if resume is not None:
            result = _graph.invoke(Command(resume=resume), config=config)
        else:
            result = _graph.invoke(payload, config=config)
    interrupts = result.get("__interrupt__")
    if interrupts:
        return {
            "status": "interrupt",
            "interrupts": [i.value if hasattr(i, "value") else i for i in interrupts],
        }
    return {"status": "done", "data": _aggregate(result)}


@router.post("/run")
def run(req: RunRequest) -> Dict[str, Any]:
    """发起一次全流程（同步）；遇人工确认点返回 interrupt 供前端交互。"""
    tid = uuid.uuid4().hex
    state: Dict[str, Any] = {"user_goal": req.user_goal}
    if req.profile is not None:
        state["profile"] = req.profile.model_dump()
    state["target_jobs"] = [j.model_dump() for j in req.target_jobs]
    if req.submission_input:
        state["submission_input"] = req.submission_input
    if req.config:
        state["config"] = req.config
    out = _step(tid, state)
    return {"thread_id": tid, **out}


@router.post("/run/resume")
def resume(req: ResumeRequest) -> Dict[str, Any]:
    """继续被中断的流程（用户答复 interrupt 内容）。"""
    out = _step(req.thread_id, None, resume=req.resume)
    return {"thread_id": req.thread_id, **out}
