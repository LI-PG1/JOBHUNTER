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

# 数量硬性约束（§3.5，用户确认 2026-08-14）：无实习 2 / 有实习 1（一页版）；两页版 0 实习 3 / 1 实习 2 / 2 实习 1
# 与 rules/projects/mapping.json `quantity_table`、tests/logic_check.py 断言一致
PROJECT_COUNT_TABLE: dict[str, dict[int, int]] = {
    "one-page": {0: 2, 1: 1, 2: 1},
    "two-pages": {0: 3, 1: 2, 2: 1},
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


# ---------------------------------------------------------------- 内容级规则审核（⑧-⑪，review 回路消费，零 LLM）
# 来源：《简历内容生成规范-resume_agent.md》§三 3.1 —— 迁移 latex-lab 约束 6/7~13/24/《数字口径》。
# 与 check_resume（输入格式校验，抛 AppError）不同：本组为**内容质量**确定性检查，
# 返回 issue 列表（blocker → 触发重写；warning → 提示），不抛异常。

# 口径枚举（§2.3）：LLM 生成时自报口径，本函数检查文本中是否携带口径词
_SCOPE_KEYWORDS = (
    "评估集", "测试集", "评测集", "评测", "受控", "压测", "监控", "聚合",
    "试点", "对比", "基线", "统计", "吞吐", "并发", "延迟", "日志",
    "线上", "真实流量", "压力测试",
)
# 无量纲定性词（有词无数字 → 口径 blocker）
_VAGUE_WORDS = ("大幅", "明显", "显著", "极大", "很好", "良好", "较好", "较快", "大幅提升", "明显提升", "有效提升")
# T 目标方向词
_TARGET_POS = ("≥", ">=", "不低于", "至少", "达到", "提升至")
_TARGET_NEG = ("≤", "<=", "不高于", "控制在", "降到", "降至", "低于")

_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|％|倍|x|X)?")
_PCT = ("%", "％")

# 密度下限（§2.6，等效字）：实习要点 ≥45 / 项目条目 ≥35；组内相对 ≥0.75
DUTY_MIN_EFF = 45.0
ITEM_MIN_EFF = 35.0
REL_DENSITY = 0.75


def effective_width(text: str) -> float:
    """等效字宽：CJK 计 1.0、ASCII 计 0.55（对齐 latex-lab `_eff_w`，密度口径统一）。"""
    return sum(1.0 if ord(ch) > 0x2E7F else 0.55 for ch in text)


def _extract_numbers(text: str) -> list:
    """提取（数值, 单位）列表；跳过年份等四位上下文无关整数。"""
    out = []
    for m in _NUM_RE.finditer(text):
        raw, unit = m.group(1), m.group(2) or None
        num = float(raw)
        if unit is None and raw.isdigit() and len(raw) == 4 and 1000 <= num <= 2999:
            continue  # 年份/版本号
        out.append((num, unit))
    return out


def _issue(code: str, block: str, severity: str, message: str, index=None) -> dict:
    item = {"code": code, "block": block, "severity": severity, "message": message}
    if index is not None:
        item["index"] = index
    return item


def _period(start: Optional[str], end: Optional[str]):
    if not (start and end and is_valid_month(start) and is_valid_month(end)):
        return None
    return _month_key(start), _month_key(end)


def check_time_constraints(resume: Resume) -> list:
    """⑨ 时间约束：倒序 / 无重叠 / 项目⊆实习（与所有实习均无交叠的项目视为独立经历，豁免）。"""
    issues = []

    def _order(entries, label, s_key):
        starts = [m for x in entries if is_valid_month((m := getattr(x, s_key)))]
        for i in range(len(starts) - 1):
            if starts[i] < starts[i + 1]:
                issues.append(_issue("time_order", label, "warning",
                                     f"{label}未按时间倒序（第 {i + 1} 段晚于第 {i + 2} 段）"))
                break

    def _overlap(entries, label, s_key, e_key):
        periods = [p for x in entries if (p := _period(getattr(x, s_key), getattr(x, e_key)))]
        for i in range(len(periods)):
            for j in range(i + 1, len(periods)):
                a, b = periods[i], periods[j]
                if a[0] < b[1] and b[0] < a[1]:
                    issues.append(_issue("time_overlap", label, "blocker",
                                         f"{label}时间重叠（第 {i + 1} 段与第 {j + 1} 段）"))

    _order(resume.education, "education", "start_month")
    _order(resume.internship, "internship", "start_month")
    _order(resume.project, "projects", "start_month")
    _overlap(resume.education, "education", "start_month", "end_month")
    _overlap(resume.internship, "internship", "start_month", "end_month")
    _overlap(resume.project, "projects", "start_month", "end_month")

    # 项目 ⊆ 实习（有实习时；无交叠的独立项目豁免）
    if resume.internship:
        ip = [p for it in resume.internship if (p := _period(it.start_month, it.end_month))]
        for i, pr in enumerate(resume.project):
            pp = _period(pr.start_month, pr.end_month)
            if not pp:
                continue
            overlapped = [x for x in ip if pp[0] < x[1] and x[0] < pp[1]]
            if not overlapped:
                continue
            if not any(pp[0] >= x[0] and pp[1] <= x[1] for x in overlapped):
                issues.append(_issue("project_not_in_internship", "projects", "blocker",
                                     f"项目「{pr.name}」与实习时间交叠但未完全包含于实习区间", i))
    return issues


def check_star_chain(block: str, index: int, items: list) -> list:
    """⑧ S→T→R 逻辑链：S 含基线数字、T 含量化目标、R ≥/≤ T（同单位百分比可提取时零 LLM）。"""
    if len(items) < 4:
        # 方案 A 定稿（2026-08-17）：一页恒 4 条 S/T/A/R，条数不足即 STAR 不完整 → blocker
        return [_issue("star_chain", block, "blocker",
                       f"要点条数 {len(items)} 不足 STAR 四段（S/T/A/R 各需 1 条）", index)]
    issues = []
    s_text = items[0][1]
    t_text = items[1][1]
    r_text = items[3][1]
    edited_any = any(it[2] for it in items[:4])
    severity = "warning" if edited_any else "blocker"  # edited 锁定条不可重写，降为提示

    s_nums = _extract_numbers(s_text)
    t_nums = _extract_numbers(t_text)
    r_nums = _extract_numbers(r_text)

    if not s_nums:
        issues.append(_issue("star_chain", block, severity, "S 背景缺基线数字（现状/痛点量化）", index))
    if not t_nums:
        issues.append(_issue("star_chain", block, severity, "T 目标缺量化数字（须与 R 呼应）", index))
    elif not any(w in t_text for w in _TARGET_POS + _TARGET_NEG):
        issues.append(_issue("star_chain", block, severity, "T 目标缺目标语义（≥/≤/控制在/达到等）", index))
    if not r_nums:
        issues.append(_issue("star_chain", block, severity, "R 结果缺量化数字", index))

    # R vs T：同为百分比时比较（仅当 T 含 NEG 目标词且不含 POS 词时按上限判断；否则按下限）
    t_pcts = [n for n, u in t_nums if u in _PCT]
    r_pcts = [n for n, u in r_nums if u in _PCT]
    if t_pcts and r_pcts:
        neg = any(w in t_text for w in _TARGET_NEG) and not any(w in t_text for w in _TARGET_POS)
        t_v, r_v = max(t_pcts), max(r_pcts)
        if neg and r_v > t_v:
            issues.append(_issue("star_chain", block, severity, f"R 结果未达 T 上限目标（{r_v:g}% > {t_v:g}%）", index))
        elif not neg and r_v < t_v:
            issues.append(_issue("star_chain", block, severity, f"R 结果未达 T 目标（{r_v:g}% < {t_v:g}%）", index))
    return issues


def check_density(block: str, index: int, texts: list, min_eff: float) -> list:
    """⑩ 密度均衡：单条绝对下限 + 组内相对 ≥0.75（等效字，跳过 edited 锁定条）。"""
    issues = []
    effs = [(i, effective_width(t), ed) for i, t, ed in texts]
    for i, w, ed in effs:
        if not ed and w < min_eff:
            issues.append(_issue("density_min", block, "blocker",
                                 f"单条等效字 {int(w)} 低于下限 {int(min_eff)}", index))
    active = [w for _, w, ed in effs if not ed]
    if active:
        base = max(active)
        for i, w, ed in effs:
            if not ed and base > 0 and w / base < REL_DENSITY:
                issues.append(_issue("density_balance", block, "warning",
                                     f"条目等效字 {int(w)} 低于组内最详细 {int(base)} 的 {REL_DENSITY:.0%}", index))
    return issues


def check_metric_scope(block: str, index: int, texts: list) -> list:
    """⑪ 数字口径：百分比数值合法性（blocker）；无量纲定性词（blocker）；口径词缺失（warning）。"""
    issues = []
    for i, text, ed in texts:
        if ed:
            continue
        nums = _extract_numbers(text)
        if not nums:
            if any(w in text for w in _VAGUE_WORDS):
                issues.append(_issue("metric_scope", block, "blocker",
                                     f"条目含定性程度词但无量化的数字（{text[:30]}…）", index))
            continue
        for num, unit in nums:
            if unit in _PCT and not 0 <= num <= 100:
                issues.append(_issue("metric_scope", block, "blocker",
                                     f"百分比数值异常：{num:g}%（{text[:30]}…）", index))
        if not any(k in text for k in _SCOPE_KEYWORDS):
            issues.append(_issue("metric_scope", block, "warning",
                                 f"量化数字缺口径（评估集/压测/监控聚合等，{text[:30]}…）", index))
    return issues


def rule_check_content(resume: Resume) -> list:
    """内容级规则审核 ⑧-⑪（零 LLM，review 回路消费）。

    输入：已生成/已回写的 Resume（含 items/duties 内容）；
    返回：issue 列表，`severity == "blocker"` 触发板块重写，`"warning"` 仅提示。
    block 名对齐板块契约：education / internship / projects / summary / skill_extend。
    """
    issues = check_time_constraints(resume)
    for i, pr in enumerate(resume.project):
        items = [(j, it.text, it.edited) for j, it in enumerate(pr.items)]
        issues += check_star_chain("projects", i, items)
        issues += check_density("projects", i, items, ITEM_MIN_EFF)
        issues += check_metric_scope("projects", i, items)
    for i, it in enumerate(resume.internship):
        duties = [(j, d.text, d.edited) for j, d in enumerate(it.duties)]
        issues += check_density("internship", i, duties, DUTY_MIN_EFF)
        issues += check_metric_scope("internship", i, duties)
    return issues
