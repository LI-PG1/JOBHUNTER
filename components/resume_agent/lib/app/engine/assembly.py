"""模板装配（契约 §6 building 步骤 1 / §5.5 编辑锁定展示 / §5.3 预算基线）。

P5 落地：
- 依据 pageOption 选择模板（resume-1page/2pages.html），保留 head（含 ATS 样式），重建 body：
  占位符替换、空区块删除（实习/荣誉未填充整段不输出）、照片位注入、density 档、水印模式。
- 产出 (html, config)：config 携带板块自估行数基线（estimatedLines 汇总），
  供前端实测后经 /api/adjust 回写校准（§5.3 record_actual）。
- 模板缺失为致命错误（E_TEMPLATE，§5.6）。
"""
import html as _html
import math
from pathlib import Path
from typing import Optional, Tuple

from ..core.errors import AppError, E_TEMPLATE
from .budget import BudgetTracker

TEMPLATE_FILES = {"one-page": "resume-1page.html", "two-pages": "resume-2pages.html"}
DENSITY_ORDER = ["compact", "normal", "loose"]   # 紧凑 → 松散（adjust 移动档位）
WATERMARK_TEXT = "本简历部分内容由 AI 生成，请确认真实性后再投递"
SKILL_CATEGORY_ORDER = ["专业技能", "工具与框架", "语言能力"]

# 荣誉等分行的全角字符预算（含分隔符「 · 」与年份，如「香港城市大学研究生入学奖学金 · 2026」）。
# 等分列宽 = (页面宽 - 2×边距) / 4；两页版字号 10.5pt（loose）约 3.7mm/字 → 每列约 10.7 字。
# 实测：12 字荣誉名（香港城市大学研究生入学奖学金）单列放不下折行 → 引擎按预算截断。
_HONOR_UNIT = 3.7        # 每全角字符宽度（mm，两页版 loose 字号 10.5pt 实测）
_HONOR_TIME_EXTRA = 1.5  # 「 · 2026」等时间后缀占用（全角字单位）
_HONOR_ELLIPSIS = "…"

# 荣誉名机构/赛事简称映射（有序子串替换，长词在前；未命中走预算截断）
_HONOR_ABBR_MAP = [
    # 高校（6 字以上在前，避免「香港城市大学」被「香港」类误截）
    ("中国科学技术大学", "中科大"),
    ("哈尔滨工业大学", "哈工大"),
    ("北京航空航天大学", "北航"),
    ("北京理工大学", "北理工"),
    ("西安交通大学", "西安交大"),
    ("上海交通大学", "上海交大"),
    ("中国人民大学", "人大"),
    ("大连理工大学", "大工"),
    ("西北工业大学", "西工大"),
    ("电子科技大学", "电子科大"),
    ("香港城市大学", "港城大"),
    ("香港理工大学", "港理工"),
    ("香港科技大学", "港科大"),
    ("香港中文大学", "港中大"),
    ("武汉大学", "武大"),
    ("华中科技大学", "华科"),
    ("中山大学", "中大"),
    ("厦门大学", "厦大"),
    ("四川大学", "川大"),
    ("山东大学", "山大"),
    ("吉林大学", "吉大"),
    ("兰州大学", "兰大"),
    ("东南大学", "东大"),
    ("天津大学", "天大"),
    ("同济大学", "同济"),
    ("重庆大学", "重大"),
    ("湖南大学", "湖大"),
    ("中南大学", "中南"),
    ("北京大学", "北大"),
    ("清华大学", "清华"),
    ("浙江大学", "浙大"),
    ("复旦大学", "复旦"),
    ("南京大学", "南大"),
    # 赛事/奖项（含机构前缀的荣誉名）
    ("全国大学生数学建模竞赛", "全国数模竞赛"),
    ("美国大学生数学建模竞赛", "美赛"),
    ("大学生数学建模竞赛", "数模竞赛"),
    ("数学建模竞赛", "数模竞赛"),
    ("全国大学生英语竞赛", "全国英语竞赛"),
    ("研究生入学奖学金", "研究生奖学金"),
    ("省级一等奖", "省一等奖"),
    ("省级二等奖", "省二等奖"),
    ("省级三等奖", "省三等奖"),
    ("国家级一等奖", "国一等奖"),
]

# 各页面选项排版参数（mm/pt，与模板 CSS 完全一致）：
# 一页版 resume-1page.html：@page margin 12mm；两页版 resume-2pages.html：@page margin 18mm。
# 字号/行距/区块间距/列表缩进来自对应模板的 body[data-density] 样式。
_LAYOUT = {
    "one-page": {
        "width": 210.0, "height": 297.0, "margin": 12.0,
        "fixed": {   # 固定大小元素（mm，浏览器实测校准）：抬头/联系方式/板块标题/条目头/水印/安全留白
            "header": 10.0, "contact": 8.0, "secTitle": 5.8, "itemHead": 3.2,
            "watermark": 8.0, "safe": 4.0,
        },
        # 模板固定间距（px，对应 CSS）：.item{margin-top} / .item-body{margin-top} /
        # .duty-overview{margin-top} / .skill-row、.honor{margin-top}
        "itemMarginPx": 6, "bodyMarginPx": 1, "overviewMarginPx": 2, "rowMarginPx": 3,
        "density": {   # compact / normal / loose（对应模板 data-density 档，与 resume-1page.html CSS 同步）
            "compact": {"fontPt": 8.5, "lheight": 1.24, "gapPx": 6, "liIndentPx": 10, "liMarginPx": 0},
            "normal": {"fontPt": 9.0, "lheight": 1.30, "gapPx": 9, "liIndentPx": 14, "liMarginPx": 1},
            "loose": {"fontPt": 9.5, "lheight": 1.40, "gapPx": 14, "liIndentPx": 18, "liMarginPx": 3},
        },
    },
    "two-pages": {
        "width": 210.0, "height": 594.0, "margin": 18.0, "pages": 2,
        "fixed": {
            "header": 13.0, "contact": 10.0, "secTitle": 6.3, "itemHead": 3.7,
            "watermark": 12.0, "safe": 6.0,
        },
        "itemMarginPx": 9, "bodyMarginPx": 2, "overviewMarginPx": 3, "rowMarginPx": 3,
        "density": {   # 与 resume-2pages.html CSS 同步
            "compact": {"fontPt": 9.5, "lheight": 1.4, "gapPx": 9, "liIndentPx": 12, "liMarginPx": 1},
            "normal": {"fontPt": 10.0, "lheight": 1.5, "gapPx": 14, "liIndentPx": 16, "liMarginPx": 2},
            "loose": {"fontPt": 10.5, "lheight": 1.62, "gapPx": 20, "liIndentPx": 20, "liMarginPx": 4},
        },
    },
}

# 特殊行高的板块（模板独立 line-height；技能行一页继承 body 行高，两页独立 1.6）
_SKILL_LH = {"one-page": None, "two-pages": 1.6}   # None → 继承 body[data-density] --lheight
_OVERVIEW_LH = {"one-page": 1.5, "two-pages": 1.6}
_SUMMARY_LH = {"one-page": 1.5, "two-pages": 1.7}

_PT2MM = 25.4 / 72.0    # pt → mm
_PX2PT = 0.75           # px → pt
_SAFETY = 1.2           # 内容波动安全系数（LLM 输出长度波动；估算已含行高/边距结构性校准）
_EST_SCALE = 0.80       # 估算校准系数（K 系数：浏览器实测反推，估算高度 ≈ 实际渲染；一页/两页共用）


def _content_usage(resume: dict, page_option: str, density: str, watermark: bool) -> dict:
    """按目标密度档排版参数模拟分页，估算内容所需页数与末页填充度。

    估算要素对应模板真实排版（§6.9 布局标准化）：
    - 字号 → 每行可容纳中文字符数（全角字宽 ≈ 字号）；
    - 行间距 → 行高（字号 × line-height，技能/概述/自我评价取模板独立行高）；
    - 上下/左右留白 → 页面可用高度/宽度（A4 减边距，一页 12mm / 两页 18mm）；
    - 固定大小元素（抬头、联系方式、板块标题、水印、安全留白）单独占用；
    - 分页模拟：条目带 page-break-inside:avoid，放不下整块推至下一页，空隙计入损耗
      （还原「板块标题孤悬 + 大条目推页」导致的末尾空白，用于防空白/防溢出判断）。
    """
    geo = _LAYOUT.get(page_option, _LAYOUT["one-page"])
    style = geo["density"].get(density, geo["density"]["normal"])
    fixed = geo["fixed"]
    usable_w = geo["width"] - 2 * geo["margin"]          # 左右留白后可用宽
    usable_h = geo["height"] - 2 * geo["margin"]         # 上下留白后可用高
    cpl = max(1, int(usable_w / (style["fontPt"] * _PT2MM)))   # 字号 → 每行中文字数
    lh = style["fontPt"] * style["lheight"] * _PT2MM           # 字号 × 行距 → 行高
    gap = style["gapPx"] * _PX2PT * _PT2MM                     # 区块间距（--gap）
    li_cut = max(1, int((style["liIndentPx"] * _PX2PT * _PT2MM) / (style["fontPt"] * _PT2MM)))  # 缩进折合的字符数
    item_margin = geo.get("itemMarginPx", 9) * _PX2PT * _PT2MM      # .item{margin-top}
    body_margin = geo.get("bodyMarginPx", 2) * _PX2PT * _PT2MM      # .item-body{margin-top}
    li_margin = style.get("liMarginPx", 2) * _PX2PT * _PT2MM        # .item-body li、ul{margin-top}
    row_margin = geo.get("rowMarginPx", 3) * _PX2PT * _PT2MM        # .skill-row/.honor{margin-top}
    ov_margin = geo.get("overviewMarginPx", 3) * _PX2PT * _PT2MM    # .duty-overview{margin-top}
    footer_h = 8.0 if page_option == "two-pages" else 0.0           # 两页版 .page-footer（margin+padding+行高）
    lh_skill = style["fontPt"] * (_SKILL_LH.get(page_option) or style["lheight"]) * _PT2MM
    lh_ov = style["fontPt"] * _OVERVIEW_LH.get(page_option, 1.5) * _PT2MM
    lh_sum = style["fontPt"] * _SUMMARY_LH.get(page_option, 1.5) * _PT2MM
    sec_h = fixed["secTitle"] + gap

    def eff_w(s: str) -> float:               # 等效中文字宽（中文 1.0 / ASCII≈0.55，与生成规范 §2.6 一致）
        return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in str(s or ""))

    def tlines(text, li=False) -> int:
        w = max(1, cpl - (li_cut if li else 0))
        n = math.ceil(eff_w(text) / w)
        return max(1, n)

    blocks = []                       # [(高度 mm, 是否 avoid 条目, 板块名)]
    blocks.append((fixed["header"] + fixed["contact"], False, "header"))

    def add_section(name, item_blocks):
        if not item_blocks:
            return
        # 板块标题与首个条目绑定为一块（keep-with-next：标题不孤悬页尾，
        # 与模板 .sec-title{page-break-after:avoid} 保持一致）
        first_h, first_avoid = item_blocks[0]
        blocks.append((sec_h + first_h, first_avoid, name))
        blocks.extend((h, a, name) for h, a in item_blocks[1:])

    add_section("education", [(fixed["itemHead"] + item_margin, True)
                              for _ in (resume.get("education") or [])])                        # 教育
    # 荣誉（行内 inline 排列，按总宽度折行估算，而非每条独立一行）
    honor_names = [h.get("name") for h in (resume.get("honor") or [])
                   if str(h.get("name") or "").strip()]
    if honor_names:
        add_section("honor", [(tlines("、".join(honor_names)) * lh + row_margin, False)])
    for it in resume.get("internship") or []:                                                   # 实习（每段一个 avoid 条目）
        item_h = fixed["itemHead"] + item_margin + body_margin
        if str(it.get("overview") or "").strip():
            item_h += ov_margin + tlines(it.get("overview")) * lh_ov
        duties = it.get("duties") or []
        if duties:
            item_h += li_margin                               # ul{margin-top}
        item_h += sum(tlines(d.get("text"), li=True) * lh + li_margin
                      for d in duties)
        add_section("internship", [(item_h, True)])
    for p in resume.get("project") or []:                                                       # 项目（每个 avoid 条目）
        item_h = fixed["itemHead"] + item_margin + body_margin
        stack = [str(t) for t in (p.get("techStack") or []) if str(t).strip()]
        if stack:
            item_h += tlines("、".join(stack)) * lh           # .tech 行
        items = p.get("items") or []
        if items:
            item_h += li_margin                               # ul{margin-top}
        item_h += sum(tlines(x.get("text"), li=True) * lh + li_margin
                      for x in items)
        add_section("project", [(item_h, True)])
    # 技能（每类一行，名称过长时按多行估算）
    skill_groups: dict = {}
    for s in (resume.get("skill") or []):
        if str(s.get("name") or "").strip():
            skill_groups.setdefault(str(s.get("category") or "其他"), []).append(str(s.get("name")))
    skill_blocks = [(tlines("、".join(names)) * lh_skill + row_margin, False)
                    for names in skill_groups.values()]
    add_section("skill", skill_blocks)                                                           # 技能
    add_section("summary", [(tlines(s.get("text")) * lh_sum, False)
                            for s in (resume.get("summary") or [])])                             # 自我评价
    tail = (fixed["watermark"] if watermark else 0) + fixed["safe"] + footer_h               # 水印 + 安全留白 + 页脚
    if tail:
        blocks.append((tail, False, "tail"))

    # 估算校准：先消除结构性偏差（_EST_SCALE），再叠加内容波动余量（_SAFETY，仅内容块）
    blocks = [(h * _EST_SCALE, a, n) for h, a, n in blocks]
    blocks = [(h * _SAFETY, a, n) if not (i == 0 or i == len(blocks) - 1) else (h, a, n)
              for i, (h, a, n) in enumerate(blocks)]

    pages, last_fill = _paginate(blocks, usable_h)
    # 分页标识按单页可用高模拟（两页版总高 = 2×单页，需除以页数还原单页边界）
    page_h_single = geo["height"] / geo.get("pages", 1) - 2 * geo["margin"]
    break_section = _page_break_section(blocks, page_h_single)
    return {"pages": pages, "lastFill": last_fill, "total": usable_h,
            "breakSection": break_section}   # breakSection: 第 2 页起首板块名（两页版分页标识）


def _paginate(blocks, page_h: float):
    """模拟分页：avoid 条目放不下整块推页（空隙计入页数），返回 (页数, 末页填充度)。"""
    cur = 0.0
    pages = 1
    for h, avoid, _name in blocks:
        h = min(h, page_h)                    # 防御：单块超页按整页计
        if avoid and cur > 0 and cur + h > page_h:
            pages += 1
            cur = h
            continue
        if cur + h > page_h:
            pages += 1
            cur = h
        else:
            cur += h
    return pages, (cur / page_h if page_h else 1.0)


def _page_break_section(blocks, page_h: float) -> Optional[str]:
    """两页版分页标识：模拟分页，返回第 2 页起首板块名（header/tail 不参与）。

    与 _paginate 同口径：avoid 条目放不下整块推页；header（首块）恒在第 1 页，
    找到第一个「完整落在第 2 页」的板块即分页点，用于装配插入可见分页线。
    """
    cur = 0.0
    for h, avoid, name in blocks:
        h = min(h, page_h)
        if avoid and cur > 0 and cur + h > page_h:
            if name not in ("header", "tail"):
                return name
            cur = h
            continue
        if cur + h > page_h:
            if name not in ("header", "tail"):
                return name
            cur = h
        else:
            cur += h
    return None


def _auto_density(page_option: str, resume: dict, requested: str, watermark: bool = True) -> str:
    """按内容占用（字号/行距/留白参数化 + 分页模拟）双向调节密度档：
    内容太空 → 升档填充（防末尾大面积空白）；过满（超出目标页数）→ 降档压缩（防溢出）。"""
    expect = 1 if page_option == "one-page" else 2
    idx = DENSITY_ORDER.index(requested) if requested in DENSITY_ORDER else 1

    def sim(i):
        u = _content_usage(resume, page_option, DENSITY_ORDER[i], watermark)
        return u["pages"], u["lastFill"]

    pages, last = sim(idx)
    if pages > expect:                                        # 超出目标页数 → 降档压缩
        while idx > 0:
            idx -= 1
            pages, last = sim(idx)
            if pages <= expect:
                break
        if pages > expect:                                    # 最低档仍溢出：接受（不升回）
            return DENSITY_ORDER[idx]
        return DENSITY_ORDER[idx]
    # 太空 → 升档填充（仍不超出目标页数）
    if pages < expect or (pages == expect and last < 0.35):
        while idx < 2:
            idx += 1
            pages, last = sim(idx)
            if pages > expect or last >= 0.35:
                if pages > expect:
                    idx -= 1                                  # 升档过头则回退
                break
        return DENSITY_ORDER[idx]
    return DENSITY_ORDER[idx]


def _esc(value) -> str:
    return _html.escape(str(value or ""), quote=True)


def _time_range(start: Optional[str], end: Optional[str]) -> str:
    s, e = (start or "").strip(), (end or "").strip()
    return f"{s}—{e}" if (s or e) else ""


def load_template(templates_dir: str, page_option: str) -> str:
    name = TEMPLATE_FILES.get(page_option, TEMPLATE_FILES["one-page"])
    path = Path(templates_dir) / name
    if not path.exists():
        raise AppError(E_TEMPLATE, f"简历模板缺失: {name}")
    return path.read_text(encoding="utf-8")


class Assembler:
    """模板装配器（无状态，可复用）。"""

    def __init__(self, templates_dir: str, storage=None):
        self.templates_dir = templates_dir
        self.storage = storage

    # ------------------------------------------------------------ 入口

    def render(self, resume: dict, blocks: dict, *, density: str = "normal",
               watermark_mode: str = "practice") -> Tuple[str, dict]:
        """装配完整 HTML 与 config。blocks 用于提取自估行数基线（§5.3）。"""
        page_option = resume.get("pageOption", "one-page")
        template = load_template(self.templates_dir, page_option)
        head = template[: template.index("<body")]
        # 替换 <head> 内标题占位符（如 <title>{{姓名}}个人简历</title>）
        name = str((resume.get("basicInfo") or {}).get("name") or "").strip()
        if name:
            head = head.replace("{{姓名}}", _esc(name))

        # 板块顺序：教育经历、证书荣誉、实习经历、项目经验、技能特长、自我评价（末尾）
        # 对齐参考简历版式（企小鹅简历：教育背景→证书荣誉→实习经历→项目经验→技能特长→自我评价）；
        # 无数据时对应 _xxx 返回空串，不占位
        effective_density = _auto_density(page_option, resume, density, watermark_mode == "practice")
        sections = [("education", self._education(resume)), ("honor", self._honor(resume)),
                    ("internship", self._internship(resume)), ("project", self._projects(resume)),
                    ("skill", self._skills(resume)), ("summary", self._summary(resume, page_option))]
        parts = [self._header(resume), self._contact(resume)]
        # 两页版分页标识：在估算的第 2 页起首板块前插入可见分页线（页面预览可分辨分页位置）
        break_section = None
        if page_option == "two-pages":
            usage = _content_usage(resume, page_option, effective_density, watermark_mode == "practice")
            break_section = usage.get("breakSection")
        for sec_name, part in sections:
            if sec_name == break_section and part:
                parts.append('<div class="page-mark">第 1 页 结束 · 第 2 页 开始</div>')
            if part:
                parts.append(part)
        if watermark_mode == "practice":
            parts.append(self._watermark())

        html = (head + f'<body data-density="{_esc(effective_density)}">\n'
                + "\n".join(p for p in parts if p) + "\n</body>\n</html>")

        config = {
            "pageOption": page_option,
            "density": effective_density,
            "requestedDensity": density,
            "direction": resume.get("direction", ""),
            "contentPlan": resume.get("contentPlan") or {},
            "blocks": self._estimated_baseline(blocks),
        }
        return html, config

    # ------------------------------------------------------------ 头部/联系

    def _header(self, resume: dict) -> str:
        basic = resume.get("basicInfo") or {}
        name = _esc(basic.get("name"))
        photo = self._photo(resume.get("photo") or {})
        return (
            '<div class="header">\n'
            f'  <div class="name">{name}个人简历</div>\n'
            f"  {photo}\n"
            "</div>"
        )

    def _photo(self, photo: dict) -> str:
        # 无照片时保留占位框（虚线 + 「照片」提示，打印自动隐藏），给排版留出照片位
        if not photo or not photo.get("filePath"):
            return '<div class="photo placeholder" id="photo-slot">照片</div>'
        data_url = ""
        if self.storage is not None:
            try:
                data_url = self.storage.photo_to_data_url(photo["filePath"])
            except OSError:
                data_url = ""
        if not data_url:
            return '<div class="photo empty" id="photo-slot"></div>'
        return f'<div class="photo" id="photo-slot"><img src="{data_url}" alt="照片"></div>'

    def _contact(self, resume: dict) -> str:
        basic = resume.get("basicInfo") or {}
        spans = [
            f"电话：<b>{_esc(basic.get('phone'))}</b>",
            f"邮箱：<b>{_esc(basic.get('email'))}</b>",
        ]
        if basic.get("website"):
            spans.append(f"个人网站：{_esc(basic['website'])}")
        if basic.get("base"):
            spans.append(f"所在城市：{_esc(basic['base'])}")
        if basic.get("internshipDuration"):
            spans.append(f"可实习时长：{_esc(basic['internshipDuration'])}")
        if basic.get("startAvailable"):
            spans.append(f"到岗时间：{_esc(basic['startAvailable'])}")
        body = "\n".join(f"  <span>{s}</span>" for s in spans)
        return f'<div class="contact">\n{body}\n</div>'

    # ------------------------------------------------------------ 各板块

    def _summary(self, resume: dict, page_option: str) -> str:
        sentences = [str(s.get("text", "")).strip() for s in (resume.get("summary") or [])]
        sentences = [s for s in sentences if s]
        if not sentences:
            return ""
        # 逐句渲染（§5.5）：data-block/data-index 供前端定位点击编辑
        # 对齐参考简历版式：自我评价为末尾带标题区块（一页/两页一致）
        if page_option == "two-pages":
            body = "\n".join(
                f'  <p class="summary-sentence" data-block="summary" data-index="{i}">{_esc(s)}</p>'
                for i, s in enumerate(sentences))
            return ('<div class="section" id="sec-summary">\n  <div class="sec-title">自我评价</div>\n'
                    f'  <div class="item-body">\n{body}\n  </div>\n</div>')
        body = "\n".join(
            f'  <p class="summary-sentence" data-block="summary" data-index="{i}">{_esc(s)}</p>'
            for i, s in enumerate(sentences))
        return ('<div class="section" id="sec-summary">\n  <div class="sec-title">自我评价</div>\n'
                f'  <div class="summary">\n{body}\n  </div>\n</div>')

    def _education(self, resume: dict) -> str:
        items = []
        for e in (resume.get("education") or []):
            sub = " · ".join(x for x in (_esc(e.get("major")), _esc(e.get("degree"))) if x)
            items.append(
                '  <div class="item">\n'
                '    <div class="item-head">\n'
                f'      <span class="item-title">{_esc(e.get("school"))}</span>\n'
                f'      <span class="item-sub">{sub}</span>\n'
                f'      <span class="item-time">{_esc(_time_range(e.get("startMonth"), e.get("endMonth")))}</span>\n'
                "    </div>\n"
                "  </div>"
            )
        if not items:
            return ""
        return ('<div class="section">\n  <div class="sec-title">教育背景</div>\n'
                + "\n".join(items) + "\n</div>")

    def _internship(self, resume: dict) -> str:
        items = []
        for i, it in enumerate(resume.get("internship") or []):
            overview = str(it.get("overview") or "").strip()
            ov = ""
            if overview:
                ov = (f'      <div class="duty-overview" data-block="internship" data-index="{i}" '
                      f'data-role="overview"><b>主要职责：</b>{_esc(overview)}</div>\n')
            lis = "\n".join(
                f'        <li data-block="internship" data-index="{i}" data-sub-index="{j}">{_esc(d.get("text"))}</li>'
                for j, d in enumerate(it.get("duties") or []))
            items.append(
                '  <div class="item">\n'
                '    <div class="item-head">\n'
                f'      <span class="item-title">{_esc(it.get("company"))}</span>\n'
                f'      <span class="item-sub">{_esc(it.get("position"))}</span>\n'
                f'      <span class="item-time">{_esc(_time_range(it.get("startMonth"), it.get("endMonth")))}</span>\n'
                "    </div>\n"
                f'    <div class="item-body">\n{ov}      <ul>\n{lis}\n      </ul>\n    </div>\n'
                "  </div>"
            )
        if not items:
            return ""   # 空区块删除（非常驻板块）
        return ('<div class="section" id="sec-internship">\n  <div class="sec-title">实习经历</div>\n'
                + "\n".join(items) + "\n</div>")

    def _projects(self, resume: dict) -> str:
        items = []
        for i, p in enumerate(resume.get("project") or []):
            tech = ""
            stack = [str(t) for t in (p.get("techStack") or []) if str(t).strip()]
            if stack:
                tech = f'      <div class="tech"><b>技术栈：</b>{_esc("、".join(stack))}</div>\n'
            lis = "\n".join(
                f'        <li data-block="project" data-index="{i}" data-sub-index="{j}">{_esc(x.get("text"))}</li>'
                for j, x in enumerate(p.get("items") or []))
            items.append(
                '  <div class="item">\n'
                '    <div class="item-head">\n'
                f'      <span class="item-title">{_esc(p.get("name"))}</span>\n'
                f'      <span class="item-sub">{_esc(p.get("role"))}</span>\n'
                f'      <span class="item-time">{_esc(_time_range(p.get("startMonth"), p.get("endMonth")))}</span>\n'
                "    </div>\n"
                f'    <div class="item-body">\n{tech}      <ul>\n{lis}\n      </ul>\n    </div>\n'
                "  </div>"
            )
        if not items:
            return ""
        return ('<div class="section" id="sec-projects">\n  <div class="sec-title">项目经验</div>\n'
                + "\n".join(items) + "\n</div>")

    def _skills(self, resume: dict) -> str:
        groups: dict[str, list[str]] = {}
        for s in (resume.get("skill") or []):
            cat = str(s.get("category") or "其他")
            name = str(s.get("name") or "").strip()
            if not name:
                continue
            groups.setdefault(cat, []).append(name)
        if not groups:
            return ""
        cats = sorted(groups, key=lambda c: (SKILL_CATEGORY_ORDER.index(c)
                                             if c in SKILL_CATEGORY_ORDER else len(SKILL_CATEGORY_ORDER)))
        rows = "\n".join(
            f'  <div class="skill-row"><span class="skill-cat">{_esc(c)}</span>{_esc("、".join(groups[c]))}</div>'
            for c in cats)
        return f'<div class="section" id="sec-skills">\n  <div class="sec-title">技能特长</div>\n{rows}\n</div>'

    def _honor(self, resume: dict) -> str:
        page_option = resume.get("pageOption", "one-page")
        parts = []
        for h in (resume.get("honor") or []):
            name = str(h.get("name") or "").strip()
            if not name:
                continue
            seg = " · ".join(x for x in (_esc(self._abbr_honor(name, page_option)), _esc(h.get("time"))) if x)
            parts.append(f'    <span class="honor">{seg}</span>')
        if not parts:
            return ""   # 空区块删除
        return ('<div class="section" id="sec-honors">\n  <div class="sec-title">证书荣誉</div>\n'
                '  <div class="honors">\n' + "\n".join(parts) + "\n  </div>\n</div>")

    @staticmethod
    def _abbr_honor(name: str, page_option: str) -> str:
        """荣誉名智能缩写：机构/赛事简称映射（子串替换）+ 超预算截断兜底（保持等分单行，用户定稿 2026-08-20）。"""
        abbr = name
        for full, short in _HONOR_ABBR_MAP:
            abbr = abbr.replace(full, short)
        # 等分列宽预算（全角字符）：列宽 mm / 字宽 mm，预留时间后缀
        geo = _LAYOUT.get(page_option, _LAYOUT["one-page"])
        col_mm = (geo["width"] - 2 * geo["margin"]) / 4 - 10 * _PX2PT * _PT2MM   # 减 padding-right 10px
        font_mm = geo["density"]["loose"]["fontPt"] * _PT2MM
        budget = max(4, int(col_mm / font_mm) - int(_HONOR_TIME_EXTRA))
        if len(abbr) <= budget:
            return abbr
        return abbr[:budget - 1].rstrip("、，。 ") + _HONOR_ELLIPSIS

    def _watermark(self) -> str:
        return f'<div class="watermark on" id="watermark">{_esc(WATERMARK_TEXT)}</div>'

    # ------------------------------------------------------------ 预算基线（§5.3）

    def _estimated_baseline(self, blocks: dict) -> dict:
        """各描述性板块的自估行数汇总（前端实测后与 actual 比对校准）。"""
        out = {}
        for block in ("summary", "internship", "projects"):
            output = blocks.get(block) or {}
            entries = BudgetTracker.collect_estimated(block, output)
            out[block] = sum(e["estimatedLines"] for e in entries)
        return out
