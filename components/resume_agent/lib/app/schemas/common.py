"""通用模型：枚举定稿（契约 §3.4）+ 统一响应 envelope（契约 §4.1）。"""
from enum import Enum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """契约字段采用 camelCase（basicInfo/pageOption/...）：序列化与反序列化均按 camel 别名，
    内部仍可用 snake_case 字段名访问。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class IdentityType(str, Enum):
    intern = "intern"          # 实习生
    fulltime = "fulltime"      # 全职


class VersionType(str, Enum):
    intern_version = "intern-version"   # 实习版（面向实习投递）
    fall_version = "fall-version"       # 秋招版（面向正式秋招）


class PageOption(str, Enum):
    one_page = "one-page"
    two_pages = "two-pages"


class Density(str, Enum):
    compact = "compact"
    normal = "normal"
    loose = "loose"


class DetailLevel(str, Enum):
    detailed = "详细"
    standard = "标准"
    concise = "精简"


class Criticality(str, Enum):
    critical = "critical"   # 绝不裁剪（用户手动编辑项自动 critical）
    high = "high"
    medium = "medium"
    low = "low"


class SourceType(str, Enum):
    user_input = "user-input"   # 用户原始输入
    polished = "polished"       # AI 美化（基于用户内容）
    ai_created = "ai-created"   # AI 创造（合规标记）


class Degree(str, Enum):
    bachelor = "学士"
    master = "硕士"
    doctor = "博士"
    associate = "专科"


class SkillCategory(str, Enum):
    professional = "专业技能"
    tools = "工具与框架"
    language = "语言能力"
    algorithm = "算法与模型"
    data = "数据与统计"
    engineering = "工程实践"
    certificate = "证书资质"
    interest = "兴趣爱好"
    other = "其他能力"


class SkillLevel(str, Enum):
    expert = "精通"
    proficient = "熟练"
    familiar = "熟悉"
    aware = "了解"


class SkillExtend(str, Enum):
    on = "true"
    off = "false"


class Envelope(BaseModel, Generic[T]):
    """统一响应包裹：code=0 成功；非 0 见 errors.py 错误码。"""

    code: int = 0
    message: str = "ok"
    data: Optional[T] = None
    detail: Optional[dict[str, Any]] = None
