"""写文件：匹配清单 → Markdown / HTML（简洁专业样式，含技能线标注与来源链接）。"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from ..config import WRITABLE_DIR

LINE_LABEL = {"application": "应用", "inference": "推理", "both": "双线", "other": "其他"}


def _esc(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&#39;")
    )


def to_markdown(result: dict[str, Any]) -> str:
    jobs = result.get("jobs", [])
    lines = [
        "# JS-Agent 岗位匹配结果",
        "",
        f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 画像：{_esc(result.get('profile_summary', ''))}",
        "",
        f"**{result.get('summary', '')}**",
        "",
        f"共收录 **{len(jobs)}** 个岗位（匹配度 ≥ 收录阈值，60-80% 已标「需补足」）",
        "",
    ]
    if jobs:
        lines += ["| # | 岗位 | 公司 | 城市 | 薪资 | 匹配度 | 技能线 | 状态 | 来源 |", "|---|------|------|------|------|--------|--------|------|------|"]
        for i, j in enumerate(jobs, 1):
            status = "✅" if j.get("match_score", 0) >= 80 else "⚠️ 需补足"
            link = f"[链接]({_esc(j.get('source_url',''))})" if j.get("source_url") else ""
            lines.append(
                f"| {i} | {_esc(j.get('title',''))} | {_esc(j.get('company',''))} | {_esc(j.get('city',''))} | "
                f"{_esc(j.get('salary','')) or '-'} | {j.get('match_score','-')}% | {LINE_LABEL.get(j.get('skill_line',''),'-')} | "
                f"{status} | {link} |"
            )
        lines += ["", "## 需补足岗位（60-80%）", ""]
        for j in jobs:
            if j.get("match_score", 100) < 80:
                missing = "、".join(j.get("missing_skills", []) or ["无"])
                tips = j.get("gap_tips") or ""
                lines.append(f"- **{j.get('company')} · {j.get('title')}**（{j.get('match_score')}%）缺：{missing} {('｜' + tips) if tips else ''}")
        lines += ["", "> 匹配度为系统规则打分；链接来源需投递前人工复核。", ""]
    else:
        lines += ["未收录到符合条件的岗位。"]
    return "\n".join(lines)


def to_html(result: dict[str, Any]) -> str:
    jobs = result.get("jobs", [])
    rows = []
    for i, j in enumerate(jobs, 1):
        score = j.get("match_score", 0)
        status = "ok" if score >= 80 else "gap"
        status_txt = "已收录" if score >= 80 else "需补足"
        link = f'<a href="{_esc(j.get("source_url",""))}" target="_blank">查看</a>' if j.get("source_url") else "-"
        rows.append(
            "<tr>"
            f"<td class='idx'>{i}</td>"
            f"<td class='job'>{_esc(j.get('title',''))}</td>"
            f"<td>{_esc(j.get('company',''))}</td>"
            f"<td>{_esc(j.get('city',''))}</td>"
            f"<td>{_esc(j.get('salary','')) or '-'}</td>"
            f"<td class='score'>{score}%</td>"
            f"<td><span class='line line-{j.get('skill_line','other')}'>{LINE_LABEL.get(j.get('skill_line',''),'-')}</span></td>"
            f"<td><span class='st st-{status}'>{status_txt}</span></td>"
            f"<td>{link}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows) or '<tr><td colspan="9">未收录到符合条件的岗位</td></tr>'
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>JS-Agent 岗位匹配结果</title>
<style>
  body{{font-family:'Segoe UI','Microsoft YaHei',sans-serif;margin:24px;color:#1a2230;background:#f5f7fa}}
  .card{{max-width:1200px;margin:0 auto;background:#fff;border-radius:10px;padding:28px;box-shadow:0 2px 10px rgba(27,58,92,.08)}}
  h1{{color:#1B3A5C;font-size:22px;margin:0 0 6px}} .meta{{color:#4a5568;font-size:13px;margin-bottom:12px}}
  .summary{{background:#eef4fb;border-left:5px solid #2E6FBF;padding:12px 16px;border-radius:6px;margin:12px 0}}
  table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:14px}}
  th{{background:#1B3A5C;color:#fff;padding:9px 10px;text-align:left;font-weight:600}}
  td{{padding:8px 10px;border-bottom:1px solid #e8edf3}}
  tr:nth-child(even){{background:#f8fafc}} tr:hover{{background:#eef4fb}}
  .idx{{color:#2E6FBF;font-weight:700;text-align:center;width:36px}}
  .job{{font-weight:600}} .score{{font-weight:700;color:#1B3A5C}}
  .line{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px}}
  .line-application{{background:#e3f5e8;color:#177b3a}} .line-inference{{background:#efe6fb;color:#6a34b8}}
  .line-both{{background:#fdf3d8;color:#8a6116}} .line-other{{background:#eee;color:#555}}
  .st{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px}}
  .st-ok{{background:#e3f5e8;color:#177b3a}} .st-gap{{background:#fdf3d8;color:#8a6116}}
  a{{color:#2E6FBF;text-decoration:none}} a:hover{{text-decoration:underline}}
  .foot{{color:#8a94a6;font-size:12px;margin-top:16px}}
</style></head><body>
<div class="card">
  <h1>JS-Agent 岗位匹配结果</h1>
  <div class="meta">生成时间：{date} ｜ 共收录 {len(jobs)} 个岗位（匹配度 ≥ 收录阈值，60-80% 标「需补足」）</div>
  <div class="summary">{_esc(result.get('summary',''))}</div>
  <table>
    <thead><tr><th>#</th><th>岗位</th><th>公司</th><th>城市</th><th>薪资</th><th>匹配度</th><th>技能线</th><th>状态</th><th>来源</th></tr></thead>
    <tbody>
    {rows_html}
    </tbody>
  </table>
  <div class="foot">匹配度为系统规则打分；链接来源需投递前人工复核。本结果由 JS-Agent 生成。</div>
</div>
</body></html>"""


def save(result: dict[str, Any], fmt: str = "md") -> Path:
    """写入 output/ 目录，返回文件路径。"""
    out_dir = WRITABLE_DIR / "output"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"匹配结果_{ts}.{fmt}"
    content = to_markdown(result) if fmt == "md" else to_html(result)
    path.write_text(content, encoding="utf-8")
    return path
