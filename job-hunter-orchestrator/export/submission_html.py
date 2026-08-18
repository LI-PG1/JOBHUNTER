"""Q10e 投递清单 HTML 导出：复用用户范本（投递/深圳AI岗位目标公司清单_实习版_横版.html）的视觉系统与结构。

- 纯确定性渲染（无 LLM）：submission_plan.items → 单文件 HTML（A4 横向打印即得纸质/PDF 清单）
- 范本要素：CSS 变量色板 / hero 渐变页眉 / toc 目录 / legend 图例 / tier 分组表格 / sources 双栏来源 / @media print
- 范本路径：D:\\TRAE\\WORKSPACE\\投递\\深圳AI岗位目标公司清单_实习版_横版.html（Q10e 已学习，2026-08-17）
- 设计文档：《投递清单生成设计.md》§4 导出呈现
"""
import datetime
import html
from pathlib import Path
from typing import Any, Dict, List

# ---------- 范本设计系统（CSS 提炼自范本，保持 A4 横向 + 打印适配） ----------
_CSS = """<style>
:root {
    --c-primary:#1B3A5C; --c-primary-2:#2E6FBF; --c-primary-bg:#EAF2FB;
    --c-accent:#0E9F8B; --c-text:#1A2230; --c-text-2:#4A5568; --c-text-3:#8A94A6;
    --c-line:#E2E8F0; --c-bg:#F4F6F9; --c-card:#FFFFFF; --c-row-alt:#F8FAFC;
    --c-ok:#166534; --c-ok-bg:#E3F4E8; --c-warn:#92600A; --c-warn-bg:#FDF3D8;
    --c-info:#6D28D9; --c-info-bg:#F3E9FB;
    --fs-hero:22px; --fs-h2:16px; --fs-body:14px; --fs-cell:13px; --fs-cap:12px;
    --lh-body:1.7; --lh-tight:1.5;
    --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px; --sp-6:32px;
    --rd-card:10px; --rd-pill:999px;
}
@page { size: A4 landscape; margin: 10mm 8mm; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html { background: var(--c-bg); }
body { font-family:"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif; color:var(--c-text); font-size:var(--fs-body); line-height:var(--lh-body); }
.page { max-width:1400px; margin:0 auto; background:var(--c-card); padding:var(--sp-5) var(--sp-5) var(--sp-6); box-shadow:0 1px 8px rgba(27,58,92,.08); }
a { color: var(--c-primary-2); }
.hero { background:linear-gradient(120deg,var(--c-primary) 0%,#24496f 60%,var(--c-primary-2) 130%); color:#fff; border-radius:var(--rd-card); padding:20px 26px; margin-bottom:var(--sp-4); display:flex; justify-content:space-between; align-items:center; gap:var(--sp-5); }
.hero h1 { font-size:var(--fs-hero); font-weight:700; letter-spacing:.5px; margin-bottom:var(--sp-2); }
.hero .meta { font-size:var(--fs-cap); color:#D6E2F0; line-height:1.8; }
.hero .meta b { color:#fff; font-weight:600; }
.hero .right { flex-shrink:0; max-width:520px; }
.hero .tags { margin-top:var(--sp-3); display:flex; flex-wrap:wrap; gap:var(--sp-2); }
.hero .tag { background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.32); border-radius:var(--rd-pill); padding:3px 12px; font-size:var(--fs-cap); }
.toc { display:flex; flex-wrap:wrap; gap:var(--sp-2); padding:var(--sp-3) 0 var(--sp-4); border-bottom:1px solid var(--c-line); margin-bottom:var(--sp-4); }
.toc a { font-size:var(--fs-cap); color:var(--c-text-2); text-decoration:none; border:1px solid var(--c-line); border-radius:var(--rd-pill); padding:3px 12px; transition:all .15s; }
.toc a:hover { color:var(--c-primary-2); border-color:var(--c-primary-2); background:var(--c-primary-bg); }
.legend { display:flex; align-items:center; flex-wrap:wrap; gap:var(--sp-3); font-size:var(--fs-cap); color:var(--c-text-2); background:var(--c-bg); border:1px solid var(--c-line); border-radius:var(--rd-card); padding:var(--sp-2) var(--sp-4); margin-bottom:var(--sp-4); }
.skill { display:inline-block; padding:1px 10px; border-radius:var(--rd-pill); font-size:11.5px; font-weight:600; white-space:nowrap; }
.skill-app { background:var(--c-ok-bg); color:var(--c-ok); border:1px solid #B7E0C3; }
.skill-inf { background:var(--c-info-bg); color:var(--c-info); border:1px solid #DCC9F0; }
.skill-both { background:var(--c-warn-bg); color:var(--c-warn); border:1px solid #F0DC9C; }
h2 { font-size:var(--fs-h2); color:var(--c-primary); border-left:5px solid var(--c-primary-2); padding:4px 0 4px 12px; margin:var(--sp-5) 0 var(--sp-3); letter-spacing:.3px; page-break-after:avoid; }
h2 + p, h2 + blockquote { margin-top:0; }
blockquote { background:var(--c-primary-bg); border:1px solid #D7E3F0; border-left:4px solid var(--c-primary-2); border-radius:6px; padding:8px 14px; margin:0 0 var(--sp-3); font-size:var(--fs-cap); color:#3A4657; line-height:var(--lh-tight); }
table { width:100%; border-collapse:collapse; font-size:var(--fs-cell); line-height:var(--lh-tight); margin-bottom:var(--sp-4); }
th, td { border:1px solid var(--c-line); padding:7px 10px; vertical-align:top; text-align:left; }
th { background:var(--c-primary); color:#fff; font-weight:600; white-space:nowrap; letter-spacing:.4px; }
tbody tr:nth-child(even) td { background:var(--c-row-alt); }
tbody tr:hover td { background:var(--c-primary-bg); }
td:first-child { white-space:nowrap; font-weight:700; color:var(--c-primary); background:#F0F5FB; text-align:center; }
tbody tr:nth-child(even) td:first-child { background:#E9F1F9; }
td.skill-col { white-space:nowrap; text-align:center; }
td a { word-break:break-all; }
.sources { column-count:2; column-gap:28px; font-size:12px; line-height:1.7; }
.sources li { margin:0 0 4px; padding-left:2px; break-inside:avoid; color:var(--c-text-2); }
.sources li::marker { color:var(--c-primary-2); }
.sources a { color:var(--c-primary-2); text-decoration:none; word-break:break-all; }
.footer { margin-top:var(--sp-5); padding-top:var(--sp-3); border-top:1px dashed var(--c-line); text-align:center; font-size:var(--fs-cap); color:var(--c-text-3); }
@media print {
    html { background:#fff; }
    .page { max-width:none; box-shadow:none; padding:0; }
    .toc { display:none; }
    table { page-break-inside:auto; }
    tr { page-break-inside:avoid; }
    thead { display:table-header-group; }
    .hero, th, .skill { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
</style>"""

# ---------- 分档元信息（展示分档，纯信息不构成投递建议，设计 §2.3④） ----------
_TIER_META = {
    "P0": ("P0 · 高匹配", "final_score ≥ 90：技能/经历与岗位高度契合，可优先查看。"),
    "P1": ("P1 · 中匹配", "80 ≤ final_score < 90：部分契合，可结合自身情况判断。"),
    "P2": ("P2 · 收录", "final_score < 80：收录在案，供参考。"),
}
_TIER_ORDER = ["P0", "P1", "P2"]


def _esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def _line_badge(resume_ver: str) -> tuple:
    """resumeVer → 技能线标签（应用绿 / 推理紫 / 双线黄）。"""
    v = (resume_ver or "").lower()
    if "both" in v or "双线" in v:
        return "skill-both", "双线"
    if "inf" in v or "推理" in v:
        return "skill-inf", "推理"
    return "skill-app", "应用"


def _fmt_time(iso: str) -> str:
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _profile_brief(profile: Dict[str, Any]) -> str:
    if not profile:
        return "（画像摘要）"
    parts = []
    if profile.get("background"):
        parts.append(str(profile["background"]))
    pref = profile.get("preference") or {}
    if pref.get("direction"):
        parts.append(f"方向：{pref['direction']}")
    skills = [str(s) for s in (profile.get("skills") or [])][:4]
    if skills:
        parts.append("技能：" + " / ".join(skills))
    return " ｜ ".join(parts) if parts else "（画像摘要）"


def _row(idx: int, item: Dict[str, Any]) -> str:
    badge, label = _line_badge(item.get("resumeVer", ""))
    url = item.get("source_url") or "#"
    return (
        "<tr>"
        f"<td>{idx}</td>"
        f"<td>{_esc(item.get('company', ''))} · {_esc(item.get('title', ''))}</td>"
        f"<td>{_esc(item.get('city', ''))}</td>"
        f"<td>{_esc(item.get('channel', ''))}</td>"
        f'<td class="skill-col"><span class="skill {badge}">{label}</span></td>'
        f"<td>{item.get('final_score', '')}</td>"
        f"<td>{_esc(item.get('reason', ''))}</td>"
        f'<td><a href="{_esc(url)}">{_esc(url)}</a></td>'
        "</tr>"
    )


def _tier_section(tier: str, items: List[Dict[str, Any]]) -> str:
    if not items:
        return ""
    title, note = _TIER_META[tier]
    rows = "".join(_row(i, it) for i, it in enumerate(items, 1))
    return (
        f'<h2 id="tier-{tier}">{title}（{len(items)}）</h2>'
        f"<blockquote>{note}本清单为结构化推荐，只展示不引导；投递决定与动作由您独立完成。</blockquote>"
        "<table>"
        "<thead><tr><th>#</th><th>公司 · 岗位</th><th>城市</th><th>渠道</th><th>技能线</th><th>匹配分</th><th>推荐理由</th><th>来源链接</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _toc(plan: Dict[str, Any]) -> str:
    items = plan.get("items", [])
    present = [t for t in _TIER_ORDER if any(it.get("tier") == t for it in items)]
    links = "".join(f'<a href="#tier-{t}">{_TIER_META[t][0]}</a>' for t in present)
    if items:
        links += '<a href="#sources">来源链接</a>'
    return f'<nav class="toc">{links}</nav>' if links else ""


def _sources(plan: Dict[str, Any]) -> str:
    items = plan.get("items", [])
    if not items:
        return ""
    lis = "".join(
        f'<li>{_esc(it.get("company", ""))} · {_esc(it.get("title", ""))}：'
        f'<a href="{_esc(it.get("source_url", "#"))}">{_esc(it.get("source_url", "#"))}</a></li>'
        for it in items
    )
    return f'<h2 id="sources">来源链接</h2><ul class="sources">{lis}</ul>'


def render_submission_plan_html(plan: Dict[str, Any], resume_ver: str = "line-mock",
                                profile: Dict[str, Any] | None = None) -> str:
    """submission_plan → 单文件 HTML（A4 横向，复用范本格式）。"""
    profile = profile or {}
    items = plan.get("items", [])
    summary = plan.get("summary", {}) or {}
    by_tier = summary.get("by_tier", {}) or {}
    generated = _fmt_time(plan.get("generated_at", ""))
    badge, label = _line_badge(resume_ver)
    tag_html = "".join(
        f'<span class="tag">{t} {by_tier.get(t, 0)} 个</span>'
        for t in _TIER_ORDER if by_tier.get(t, 0)
    )

    hero = (
        '<div class="hero"><div>'
        f"<h1>{_esc(resume_ver)} 投递清单</h1>"
        f'<div class="meta">生成时间：<b>{generated}</b> ｜ 简历版本：<b>{_esc(resume_ver)}</b> ｜ 画像：<b>{_esc(_profile_brief(profile))}</b></div>'
        f'<div class="meta">候选 <b>{summary.get("total", len(items))}</b> 条 ｜ 分档：P0 <b>{by_tier.get("P0", 0)}</b> · P1 <b>{by_tier.get("P1", 0)}</b> · P2 <b>{by_tier.get("P2", 0)}</b> ｜ 状态：<b>{plan.get("status", "")}</b></div>'
        '</div><div class="right"><div class="tags">'
        f'<span class="tag">{label}线</span>{tag_html}'
        "</div></div></div>"
    )
    legend = (
        '<div class="legend"><span>技能线标注：</span>'
        '<span class="skill skill-app">应用</span><span>Agent / RAG / 微调应用主线</span>'
        '<span class="skill skill-inf">推理</span><span>推理部署 / 性能优化 / 量化压缩主线</span>'
        '<span class="skill skill-both">双线</span><span>两条线都强相关</span>'
        '<span style="margin-left:12px">说明：本清单由大脑生成，仅作投递参考（只推荐不引导）；投递由您独立完成。</span>'
        "</div>"
    )
    tiers = "".join(
        _tier_section(t, [it for it in items if it.get("tier") == t])
        for t in _TIER_ORDER
    )
    footer = (
        '<p class="footer">本页为「{ver}」版本投递清单（A4 横向，左右 8mm 留白），由 JobHunter 大脑生成。'
        "岗位时效性强、招满即止，投递前请以官方招聘页为准。打印 / 导出 PDF 时请在打印设置中选择「横向」。</p>"
    ).format(ver=_esc(resume_ver))

    return (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"<title>{_esc(resume_ver)} 投递清单</title>\n{_CSS}\n</head>\n<body>\n<div class=\"page\">\n"
        f"{hero}\n{_toc(plan)}\n{legend}\n{tiers}\n{_sources(plan)}\n{footer}\n"
        "</div>\n</body>\n</html>\n"
    )


def export_submission_plan_html(plan: Dict[str, Any], resume_ver: str = "line-mock",
                                profile: Dict[str, Any] | None = None,
                                out_dir: str | Path = ".") -> Path:
    """渲染并写文件：投递清单_<resumeVer>_<YYYYMMDD>.html。返回输出路径。"""
    html_text = render_submission_plan_html(plan, resume_ver, profile)
    fname = f"投递清单_{resume_ver}_{datetime.datetime.now():%Y%m%d}.html"
    out = Path(out_dir) / fname
    out.write_text(html_text, encoding="utf-8")
    return out
