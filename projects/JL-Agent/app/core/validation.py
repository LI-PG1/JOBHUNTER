"""数据校验层（契约 §3.3 集中实现）：时间/枚举/邮箱电话/数量上限/照片。

数量硬性约束（§3.5/§6.4 落地为代码常量表，禁止漂移）也在此定义，
供生成引擎（P4）与适配（P5）统一引用。
"""
import io
import re
from typing import Optional

from PIL import Image

from .errors import E_EDU_TIME, E_LIMIT, E_PARAM, E_PHOTO_BYTES, E_PHOTO_FORMAT, E_PHOTO_SIZE, AppError
from ..schemas import Resume

# ---------------------------------------------------------------- 数量硬性约束（§3.5）

# {page_option: {internship_count: project_count}}
# 规则（用户要求）：一段实习经历至少匹配两个项目（两页版每段实习配 2 个；一页版容量受限至少 2 个）
PROJECT_COUNT_TABLE: dict[str, dict[int, int]] = {
    "one-page": {0: 2, 1: 2, 2: 2},
    "two-pages": {0: 3, 1: 2, 2: 4},
}


def project_count_for(page_option: str, internship_count: int) -> int:
    """按页数+实习条数取项目硬性条数（零漂移）。"""
    return PROJECT_COUNT_TABLE.get(page_option, PROJECT_COUNT_TABLE["one-page"]).get(
        internship_count, 1
    )


# ---------------------------------------------------------------- 基础校验函数

MONTH_RE = re.compile(r"^\d{4}\.(0[1-9]|1[0-2])$")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
PHONE_RE = re.compile(r"^(?:\+?\d{1,3}[- ]?)?(?:\d{7,11}|\d{3,4}[- ]\d{7,8})$")


def is_valid_month(value: Optional[str]) -> bool:
    return bool(value and MONTH_RE.match(value))


def is_valid_email(value: Optional[str]) -> bool:
    return bool(value and EMAIL_RE.match(value))


def is_valid_phone(value: Optional[str]) -> bool:
    return bool(value and PHONE_RE.match(value))


def _month_key(value: str) -> tuple[int, int]:
    y, m = value.split(".")
    return int(y), int(m)


# 时间区间统一约束（用户指定）：开始与结束均限 2015.01 ~ 2030.12
MIN_START_MONTH: tuple[int, int] = (2015, 1)
MAX_END_MONTH: tuple[int, int] = (2030, 12)


def check_period(start: Optional[str], end: Optional[str], label: str) -> None:
    """时间区间校验：end > start；开始与结束均须在 2015.01 ~ 2030.12 内。"""
    if not start or not end:
        return
    if not (is_valid_month(start) and is_valid_month(end)):
        raise AppError(E_EDU_TIME, f"{label}时间格式非法（应为 YYYY.MM）")
    if _month_key(end) <= _month_key(start):
        raise AppError(E_EDU_TIME, f"{label}结束时间必须晚于开始时间")
    if _month_key(start) < MIN_START_MONTH or _month_key(end) > MAX_END_MONTH:
        raise AppError(E_EDU_TIME, f"{label}时间须在 2015 年 1 月至 2030 年 12 月之间")


# ---------------------------------------------------------------- Resume 整体校验


def check_resume(resume: Resume, limits) -> None:
    """集中校验 Resume（POST/PUT/生成前调用）。

    校验项（§3.3）：教育 ≤3 且时间合法、实习 ≤2 且时间合法、JD ≤5、
    技能 ≥1、邮箱/电话格式、项目时间合法。抛 AppError 携带明确错误码。
    """
    # 基本信息（必填项，pydantic 已约束非空；此处补格式校验）
    info = resume.basic_info
    if info:
        if not is_valid_email(info.email):
            raise AppError(E_PARAM, "邮箱格式不正确", {"field": "basicInfo.email"})
        if not is_valid_phone(info.phone):
            raise AppError(E_PARAM, "电话格式不正确", {"field": "basicInfo.phone"})

    # 教育：数量上限 + 时间区间
    if len(resume.education) > limits.education_max:
        raise AppError(E_LIMIT, f"教育背景最多 {limits.education_max} 条")
    for e in resume.education:
        check_period(e.start_month, e.end_month, "教育经历")

    # 实习：数量上限 + 时间区间
    if len(resume.internship) > limits.internship_max:
        raise AppError(E_LIMIT, f"实习经历最多 {limits.internship_max} 段")
    for it in resume.internship:
        check_period(it.start_month, it.end_month, "实习经历")

    # 项目：时间区间（条数由生成阶段按 §3.5 硬性约束）
    for p in resume.project:
        check_period(p.start_month, p.end_month, "项目经历")

    # JD：数量上限（≥1 由生成关卡校验，CRUD 允许暂不填写）
    if len(resume.jobs) > limits.jobs_max:
        raise AppError(E_LIMIT, f"目标岗位最多 {limits.jobs_max} 套")

    # 技能：必填 ≥1
    if not resume.skill:
        raise AppError(E_PARAM, "技能特长至少填写 1 条")


# ---------------------------------------------------------------- 照片校验（§4.2 upload）


def check_photo(data: bytes, filename: str, limits) -> dict:
    """照片上传校验：格式 JPG/PNG、尺寸 200~4000px、≤5MB；返回照片元数据。

    比例（3:4 / 4:5）仅提示不拦截，由前端基于返回的 ratio 提示。
    """
    if len(data) > limits.photo_max_bytes:
        raise AppError(E_PHOTO_BYTES, "照片大小超过 5MB 限制")

    fmt = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "") or "jpg"
    if fmt not in ("jpg", "jpeg", "png"):
        raise AppError(E_PHOTO_FORMAT, "仅支持 JPG/PNG 格式")
    fmt = "jpg" if fmt == "jpeg" else fmt

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise AppError(E_PHOTO_FORMAT, "无法解析图片文件，请上传有效图片")

    w, h = img.size
    if w < 200 or h < 200 or w > 4000 or h > 4000:
        raise AppError(E_PHOTO_SIZE, "照片尺寸需在 200~4000 像素之间")

    ratio = _photo_ratio(w, h)
    return {"width": w, "height": h, "ratio": ratio, "format": fmt}


def _photo_ratio(w: int, h: int) -> str:
    """最简比例；接近 3:4 / 4:5 时归一到对应档（用于前端提示）。"""
    g = _gcd(w, h)
    rw, rh = w // g, h // g
    if abs(rw / rh - 3 / 4) < 0.06:
        return "3:4"
    if abs(rw / rh - 4 / 5) < 0.06:
        return "4:5"
    return f"{rw}:{rh}"


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a or 1
