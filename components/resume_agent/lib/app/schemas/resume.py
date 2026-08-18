"""Resume 数据模型：字段契约 §3.1/§3.2（结构与类型层；业务校验集中在 core/validation.py）。"""
from datetime import datetime
from typing import List, Optional

from pydantic import Field

from .common import (
    CamelModel,
    Criticality,
    Degree,
    Density,
    DetailLevel,
    IdentityType,
    PageOption,
    SkillCategory,
    SkillLevel,
    SourceType,
    VersionType,
)
from .jobs import Job

# ---------------------------------------------------------------- 实体


class BasicInfo(CamelModel):
    name: str = Field(min_length=1, max_length=32, description="姓名")
    age: int = Field(ge=16, le=70, description="年龄")
    email: str = Field(min_length=3, description="邮箱")
    phone: str = Field(min_length=6, max_length=20, description="电话")
    website: Optional[str] = Field(default=None, max_length=200, description="个人网页")
    base: Optional[str] = Field(default=None, max_length=50, description="常驻城市")
    internship_duration: Optional[str] = Field(default=None, max_length=50, description="可实习时长")
    start_available: Optional[str] = Field(default=None, max_length=50, description="到岗时间")


class Photo(CamelModel):
    data_url: Optional[str] = None        # base64 data URL（响应用）
    file_path: Optional[str] = None       # data/photos/{id}.{ext}
    width: Optional[int] = None
    height: Optional[int] = None
    ratio: Optional[str] = None           # "3:4" | "4:5"（比例提示，不拦截）
    format: Optional[str] = None          # "jpg" | "png"


class Education(CamelModel):
    school: str = Field(min_length=1, max_length=64)
    major: str = Field(min_length=1, max_length=64)
    degree: Degree
    start_month: str = Field(pattern=r"^\d{4}\.(0[1-9]|1[0-2])$")
    end_month: str = Field(pattern=r"^\d{4}\.(0[1-9]|1[0-2])$")


class Internship(CamelModel):
    company: str = Field(min_length=1, max_length=64)
    position: str = Field(min_length=1, max_length=64)
    start_month: str = Field(pattern=r"^\d{4}\.(0[1-9]|1[0-2])$")
    end_month: str = Field(pattern=r"^\d{4}\.(0[1-9]|1[0-2])$")
    overview: Optional[str] = Field(default=None, max_length=300, description="主要职责概述（1 句）")
    duties: List["Duty"] = Field(default_factory=list, max_length=8)


class Duty(CamelModel):
    text: str = Field(min_length=1, max_length=500)
    criticality: Criticality = Criticality.low
    edited: bool = False          # 编辑锁定（§5.5）：用户手动修改 → 不可被自动重写


class Project(CamelModel):
    name: str = Field(min_length=1, max_length=64)
    role: Optional[str] = Field(default=None, max_length=32)
    start_month: Optional[str] = Field(default=None, pattern=r"^\d{4}\.(0[1-9]|1[0-2])$")
    end_month: Optional[str] = Field(default=None, pattern=r"^\d{4}\.(0[1-9]|1[0-2])$")
    tech_stack: List[str] = Field(default_factory=list, max_length=20)
    items: List["ProjectItem"] = Field(default_factory=list, max_length=12)
    source: SourceType = SourceType.user_input
    ai_flag: bool = False


class ProjectItem(CamelModel):
    text: str = Field(min_length=1, max_length=500)
    criticality: Criticality = Criticality.low
    edited: bool = False          # 编辑锁定（§5.5）


class SummarySentence(CamelModel):
    text: str = Field(min_length=1, max_length=300)
    criticality: Criticality = Criticality.low
    edited: bool = False          # 编辑锁定（§5.5）


class Skill(CamelModel):
    category: SkillCategory = SkillCategory.professional
    name: str = Field(min_length=1, max_length=64)
    level: Optional[SkillLevel] = None
    skill_extend: bool = False


class Honor(CamelModel):
    name: str = Field(min_length=1, max_length=128)
    time: Optional[str] = Field(default=None, max_length=32)
    criticality: Criticality = Criticality.low


# ---------------------------------------------------------------- 内容计划 / 生成追溯


class ContentPlan(CamelModel):
    detail_level: DetailLevel = DetailLevel.standard
    project_count: Optional[int] = None      # 数量硬性约束 §3.5（生成阶段确定）
    bullet_count_per_project: Optional[int] = None
    summary_sentence_count: Optional[int] = None


class GenerationInfo(CamelModel):
    task_id: Optional[str] = None
    stages: List[str] = Field(default_factory=list)
    watermark_mode: Optional[str] = None
    deep_search: bool = False
    calibration_ref: Optional[str] = None


# ---------------------------------------------------------------- Resume 顶层


class Resume(CamelModel):
    """契约 §3.1：顶层数据，全部板块为可选容器，必填项在 validation 层约束。"""

    id: Optional[str] = None
    version: VersionType = VersionType.intern_version
    identity: IdentityType = IdentityType.intern
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    basic_info: Optional[BasicInfo] = None
    photo: Optional[Photo] = None
    education: List[Education] = Field(default_factory=list)
    internship: List[Internship] = Field(default_factory=list)
    project: List[Project] = Field(default_factory=list)
    summary: List[SummarySentence] = Field(default_factory=list)
    skill: List[Skill] = Field(default_factory=list)
    honor: List[Honor] = Field(default_factory=list)
    jobs: List[Job] = Field(default_factory=list, description="目标岗位 JD（1~5 套，同一方向）")

    direction: Optional[str] = None
    page_option: PageOption = PageOption.one_page
    density: Density = Density.normal
    content_plan: Optional[ContentPlan] = None
    generation: Optional[GenerationInfo] = None


# 前向引用解析
Internship.model_rebuild()
Project.model_rebuild()
