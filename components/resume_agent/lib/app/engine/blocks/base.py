"""块生成基础设施（契约 §5.6 模块级失败隔离 + 自估协议规范化）。

- llm_with_degrade: 首次失败 → 重试 1 次 → 仍失败输出降级版 {"degraded": true, ...}，整单继续。
- 输出规范化：estimatedLines 夹取 1~8、criticality 缺省 low。
"""
import json
from dataclasses import dataclass, field
from typing import Any, List, Optional

from ...core.errors import AppError, E_LLM
from ..analysis import extract_json


@dataclass
class GenContext:
    """一次生成任务的共享上下文（跨块传递，无循环依赖）。"""

    task_id: str
    resume_id: str
    resume: dict                    # camelCase 简历数据快照
    jobs: list                      # camelCase Job dicts
    factsheet: dict                 # 共享事实表（§5.2）
    search_results: List[dict] = field(default_factory=list)
    search_degraded: bool = False
    page_option: str = "one-page"
    project_count: int = 0
    skill_extend_enabled: bool = False
    industry_rules: dict = field(default_factory=dict)
    blocks: dict = field(default_factory=dict)   # 各块输出
    html: str = ""                               # P5 装配产出（building）
    assembly_config: dict = field(default_factory=dict)
    review_summary: dict = field(default_factory=dict)   # reviewing 阶段审核摘要（随 task.done 返回）
    # 运行时依赖（由 runner 注入）
    provider: Optional[Any] = None
    rules: Optional[Any] = None
    storage: Optional[Any] = None
    cache: Optional[Any] = None
    analyzer: Optional[Any] = None
    budget: Optional[Any] = None
    config: Optional[Any] = None


# ---------------------------------------------------------------- LLM 失败隔离（§5.6）


async def llm_with_degrade(provider, messages, *, max_tokens: int, temperature: float,
                           degrade: dict) -> dict:
    """LLM JSON 调用 + 降级：重试 1 次后仍失败 → {**degrade, 'degraded': true}。

    捕获全部异常（含 JSON 解析 ValueError / 输出截断），确保重试生效后再降级。
    """
    for attempt in range(2):
        try:
            content = await provider.chat(messages, json_mode=True,
                                          max_tokens=max_tokens, temperature=temperature)
            return extract_json(content)
        except Exception:
            if attempt == 1:
                return {**degrade, "degraded": True}
    return {**degrade, "degraded": True}  # 理论不可达


# ---------------------------------------------------------------- 输出规范化


def clamp_estimated(value) -> int:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return 1
    return max(1, min(8, v))


def normalize_text_item(item: dict) -> dict:
    """文本条目 {text, criticality, estimatedLines} 规范化。"""
    return {
        "text": str(item.get("text", "")).strip()[:500] or "（待补充）",
        "criticality": item.get("criticality", "low") or "low",
        "estimatedLines": clamp_estimated(item.get("estimatedLines")),
    }


def as_list(value) -> List[dict]:
    if not isinstance(value, list):
        return []
    return [x for x in value if isinstance(x, dict)]


def brief_of(resume: dict) -> dict:
    """用户概要（summary 块输入）：教育/实习/技能/项目精要。"""
    edu = resume.get("education") or []
    internship = resume.get("internship") or []
    skills = [s.get("name", "") for s in (resume.get("skill") or [])]
    projects = [p.get("name", "") for p in (resume.get("project") or [])]
    return {
        "education": [f"{e.get('school','')} {e.get('major','')}（{e.get('degree','')}）" for e in edu],
        "internship": [f"{i.get('company','')} · {i.get('position','')}" for i in internship],
        "skills": skills,
        "projects": projects,
    }
