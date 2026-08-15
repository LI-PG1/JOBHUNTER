"""schemas 包：数据契约模型（契约 §3）统一出口。"""
from .common import (
    CamelModel,
    Criticality,
    Degree,
    Density,
    DetailLevel,
    Envelope,
    IdentityType,
    PageOption,
    SkillCategory,
    SkillExtend,
    SkillLevel,
    SourceType,
    VersionType,
)
from .jobs import Direction, Factsheet, Job
from .resume import (
    BasicInfo,
    ContentPlan,
    Education,
    GenerationInfo,
    Honor,
    Internship,
    Photo,
    Project,
    Resume,
    Skill,
    SummarySentence,
)
from .task import BLOCK_WEIGHTS, BlockProgress, SSEEvent, Task, TaskState

__all__ = [
    "BasicInfo", "CamelModel", "ContentPlan", "Criticality", "Degree", "Density", "DetailLevel",
    "Direction", "Education", "Envelope", "Factsheet", "GenerationInfo", "Honor",
    "IdentityType", "Internship", "Job", "PageOption", "Photo", "Project", "Resume",
    "Skill", "SkillCategory", "SkillExtend", "SkillLevel", "SourceType",
    "SummarySentence", "VersionType", "Task", "TaskState", "BlockProgress",
    "SSEEvent", "BLOCK_WEIGHTS",
]
