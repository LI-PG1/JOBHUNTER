"""适配闭环数据入口（契约 §6 / §5.3）：前端实测 → 校准 + 判定。

POST /api/adjust {taskId, measurement:{fillRatio, blocks[]}, config, round}：
  1. 每块实测行数 → budget.record_actual 追加校准行（§5.3），返回校正系数（历史中位数）
  2. 单块 |actual−estimated|/estimated > 20% → 标记超差（§5.3 误差阈值）
  3. 末页填充度判定 action（§6.7）：>100% over / <75% under / 其余 ok
  4. density 建议：over 升一档紧凑 / under 降一档松散（排版层全局生效）
  5. 上报 task.adjust 事件（§4.4，断线重连可回放），返回调整方案
"""
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import Field

from ..engine.assembly import DENSITY_ORDER
from ..engine.budget import BudgetTracker
from ..schemas import CamelModel

router = APIRouter(prefix="/api", tags=["adjust"])

# 误差阈值（§5.3）：|actual−estimated|/estimated
ERR_THRESHOLD = 0.2
# 填充度阈值（§6.7）：>1.0 溢出 / <0.75 不足
FILL_OVER = 1.0
FILL_UNDER = 0.75


class BlockMeasurement(CamelModel):
    block: str = Field(min_length=1)                     # summary/internship/projects
    actual_lines: int = Field(ge=0, le=200)
    estimated_lines: Optional[int] = Field(default=None)  # 基线（task.done config.blocks，§5.3）
    detail_level: str = "标准"
    page_width: int = 794


class Measurement(CamelModel):
    fill_ratio: float = Field(default=1.0, ge=0.0, le=2.0)   # 末页填充度（浏览器实测）
    blocks: List[BlockMeasurement] = Field(default_factory=list)


class AdjustBody(CamelModel):
    task_id: str = Field(min_length=1)
    measurement: Measurement
    config: dict = Field(default_factory=dict)   # 当前 config（含 density）
    round: int = Field(default=1, ge=1, le=3)


def _decide_action(fill_ratio: float) -> str:
    if fill_ratio > FILL_OVER:
        return "over"
    if fill_ratio < FILL_UNDER:
        return "under"
    return "ok"


def _next_density(current: str, action: str) -> str:
    """排版层档位：over → 更紧凑；under → 更松散；ok → 保持。"""
    if action not in ("over", "under"):
        return current
    try:
        idx = DENSITY_ORDER.index(current)
    except ValueError:
        return current
    nxt = idx - 1 if action == "over" else idx + 1
    if 0 <= nxt < len(DENSITY_ORDER):
        return DENSITY_ORDER[nxt]
    return current


@router.post("/adjust", response_model=dict)
async def adjust(body: AdjustBody, request: Request):
    """实测校准 + 适配判定（≤3 轮由前端控制；后端仅决策与记录）。"""
    app = request.app
    storage = app.state.storage
    storage.load_task(body.task_id)  # 40008

    budget = BudgetTracker(app.state.config.paths.data_dir)
    calibration: List[dict] = []
    drifted = False
    factor = 1.0
    for m in body.measurement.blocks:
        est = m.estimated_lines or 0
        f = budget.record_actual(m.block, m.actual_lines, m.detail_level,
                                 m.page_width, estimated_lines=m.estimated_lines)
        factor = f
        if est and abs(m.actual_lines - est) / est > ERR_THRESHOLD:
            drifted = True
        calibration.append({
            "block": m.block, "estimatedLines": est, "actualLines": m.actual_lines, "factor": f,
        })

    action = _decide_action(body.measurement.fill_ratio)
    cur_density = str((body.config or {}).get("density") or "normal")
    new_density = _next_density(cur_density, action)
    new_config = {**(body.config or {}), "density": new_density}

    # 上报 task.adjust（§4.4）：适配轮次通知（超差或需要调整时）
    task = storage.load_task(body.task_id)
    events = task.setdefault("events", [])
    events.append({
        "event": "task.adjust",
        "data": {
            "taskId": body.task_id, "round": body.round, "action": action,
            "config": new_config, "drifted": drifted,
        },
    })
    storage.save_task(task)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "action": action,
            "config": new_config,
            "factor": factor,
            "drifted": drifted,
            "calibration": calibration,
            "calibrationRef": "calibration.json",
        },
    }
