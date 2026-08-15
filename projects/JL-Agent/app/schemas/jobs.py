"""Job / JD 分析模型：共享事实表（factsheet，契约 §5.2）与职业方向。"""
from typing import List, Optional

from pydantic import Field

from .common import CamelModel, Density, DetailLevel, PageOption


class Job(CamelModel):
    """目标岗位 JD（1~5 套，同一职业方向）。"""

    title: str = Field(min_length=1, max_length=64, description="岗位名称")
    jd_text: str = Field(min_length=1, max_length=20000, description="JD 原文")
    domain_tags: List[str] = Field(default_factory=list, description="领域标签（分析后写入）")


class Direction(CamelModel):
    """JD 分析结果：职业方向，仅作为生成上下文，不在简历展示。"""

    name: str = Field(min_length=1, max_length=64)
    summary: Optional[str] = None
    core_skills: List[str] = Field(default_factory=list)
    domain_tags: List[str] = Field(default_factory=list)


class Factsheet(CamelModel):
    """共享事实表（契约 §5.2）：JD 分析唯一事实源，所有板块统一引用。"""

    version: str = "1.0"
    direction: str = ""
    identity: str = "intern"
    page_option: PageOption = PageOption.one_page
    density: Density = Density.normal
    detail_level: DetailLevel = DetailLevel.standard
    core_skills: List[str] = Field(default_factory=list)
    jd_focus: str = ""
    project_type: str = ""
    metric_style: str = ""
    quantity: dict = Field(default_factory=dict, description="数量硬性约束 §3.5")
    keyword_coverage: float = 0.0
