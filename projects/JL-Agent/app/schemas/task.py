"""任务状态机与 SSE 事件模型（契约 §4.3/§4.4）。"""
from enum import Enum
from typing import Any, Optional

from pydantic import Field

from .common import CamelModel


class TaskState(str, Enum):
    """pending → analyzing → generating → building → done；终态另含 failed/canceled。"""

    pending = "pending"
    analyzing = "analyzing"
    generating = "generating"
    building = "building"
    done = "done"
    failed = "failed"
    canceled = "canceled"


class Task(CamelModel):
    """生成任务（运行态，data/tasks/{id}.json）。"""

    id: str
    resume_id: str
    state: str = TaskState.pending
    stage: str = ""                    # analyzing/generating/building
    stage_index: int = 0
    stage_total: int = 1
    progress: float = 0.0              # 0~1
    error: Optional[dict] = None       # {code, message}
    events: list = Field(default_factory=list)  # SSE 事件持久化（断线重连可回放）
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BlockProgress(CamelModel):
    """板块进度（SSE block.progress）。"""

    task_id: str
    block: str                         # summary/education/internship/projects/skills/honor
    progress: float = Field(ge=0, le=1)


class SSEEvent(CamelModel):
    """SSE 事件载荷（event + data 结构见契约 §4.4 表格）。"""

    event: str
    data: dict[str, Any]


# 固定权重：JD 分析 15 / 自我评价 10 / 教育 5 / 实习 10 / 技能 10 / 项目 35 / 技能拓展 5 / 装配适配 10
BLOCK_WEIGHTS: dict[str, float] = {
    "analysis": 0.15,
    "summary": 0.10,
    "education": 0.05,
    "internship": 0.10,
    "skills": 0.10,
    "projects": 0.35,
    "skill_extend": 0.05,
    "build": 0.10,
}
