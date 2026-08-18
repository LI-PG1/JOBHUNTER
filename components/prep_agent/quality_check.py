"""prep_agent 质量回路·规则可查项（移植 MS quality_check.js · SOP-07）。

零 token 成本先行：正则 / 集合 diff / 上下文指纹判定，critical 命中直接回炉（LLM 无权推翻红线）。
检查项：
  D1 数字口径（基准 = 参与边界卡 + 简历；上下文指纹不一致 / 指标形态越界 → critical，基准外裸数字 → warn）
  D2 项目真实性（另一版本专属项目作为【项目】出现 → warn；基准外编造项目 → critical）
  D4 结构完整性（截断 / 一级标题 / 代码围栏破坏 → critical；组件框架缺失 → warn，v1 从简）
  D5 术语一致性（大小写混用 → warn）
"""
from __future__ import annotations

import re
from typing import Any

from prep_agent.glossary import GLOSSARY_TERMS

_DEFAULT_FILES = ["面试主线", "01_自我介绍", "02_项目深挖", "附录_数字口径"]


# ---------- 通用 ----------
def normalize_ctx(raw: str) -> str:
    """数字归一为 <N>，保留 % 后缀（is_metric_shape 依赖 <N>%），空白压缩。"""
    t = str(raw or "")
    t = re.sub(r"\d+(?:\.\d+)?\s*%", "<N>%", t)
    t = re.sub(r"\d+(?:\.\d+)?", "<N>", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_numbers(text: str) -> list[dict[str, str]]:
    """提取候选数字（含过滤：非简历指标数字——流程时长/小节号/匹配度自评/模型规模/日期等）。"""
    nums: list[dict[str, str]] = []
    text = str(text or "")
    for m in re.finditer(r"\d+(?:\.\d+)?\s*%?", text):
        raw = m.group(0)
        i = m.start()
        before = text[max(0, i - 12):i].split("\n")[-1]
        after = text[i + len(raw):i + len(raw) + 12].split("\n")[0]
        num = re.sub(r"\s*%$", "%", raw).strip()
        if re.match(r"^(?:19|20)\d{2}$", num):
            continue
        line_start = text.rfind("\n", 0, i) + 1
        prefix = text[line_start:i]
        if not prefix.strip():
            continue
        if re.match(r"^\d+[\.、．)]$", prefix.strip()):
            continue
        if re.match(r"^[（(]\d+[）)]?$", prefix.strip()):
            continue
        if re.match(r"^\d+[./-]$", prefix.strip()):
            continue
        if re.match(r"^\.$", before.strip()):
            continue
        if re.search(r"http|www|\.com|\.cn|localhost|:\d{2,}", before + after, re.I):
            continue
        if re.match(r"\d{10,}", num):
            continue
        if re.match(r"^(?:19|20)\d{2}[./-]\d{1,2}(?:[./-]\d{1,2})?$", num.strip()):
            continue
        head2 = text[max(0, i - 2):i]
        if re.match(r"^\s*[-~–]\s*\d", after) or re.match(r"\d\s*[-~–]\s*$", head2):
            continue
        if re.search(r"\d+\.\d+", num) and re.match(r"#{1,6}\s*$", prefix.strip()):
            continue
        if re.search(r"\|\s*$", prefix.strip()) and re.match(r"^\s*\|", after.strip()):
            continue
        if re.match(r"^_\S", after) and "%" not in num:
            continue
        if re.match(r"^秒", after.strip()):
            continue
        if re.search(r"[如例等][（(]?[\"“”'’]?\s*$", prefix.strip()):
            continue
        if re.search(r"陷阱\s*$", prefix.strip()):
            continue
        if re.search(r"\d/\s*$", prefix.strip()):
            continue
        if re.search(r"匹配度|契合度|相似度", before):
            continue
        if re.match(r"^\s*[→⟶⇢>]", after) or re.search(r"[→⟶⇢>]\s*$", prefix.strip()) \
                or re.match(r"%\s*[→⟶⇢>]", after):
            continue
        if re.search(r"分钟|小时|min\b|天内?|个月", after) or re.search(r"分钟|小时|min\b|天内?|个月", head2):
            continue
        if re.match(r"^\s*[KMBG]+\b", after):
            continue
        nums.append({"num": num, "ctx": normalize_ctx(before + "<N>" + after)})
    return nums


def is_metric_shape(ctx: str) -> bool:
    """指标形态判定：带 % 或 ×倍/单位/N+ 后缀才算「指标数字」（裸数字仅 warn）。"""
    if "<N>%" in ctx:
        return True
    if re.search(r"<N>[%×x+倍]", ctx):
        return True
    return bool(re.search(r"<N>(?:ms|s|GB|MB|KB|tok|tps|路|卡|万|亿|分钟?|小时|天内?|个月)", ctx))


# ---------- D1 数字口径 ----------
def check_digit_consistency(base_text: str, md_text: str, file: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    base_nums = extract_numbers(base_text)
    base_fp: dict[str, set[str]] = {}
    base_set: set[str] = set()
    for n in base_nums:
        base_set.add(n["num"])
        base_fp.setdefault(n["ctx"], set()).add(n["num"])
    for m in extract_numbers(md_text):
        if m["num"] in base_set:
            continue
        ctx_hits: set[str] | None = base_fp.get(m["ctx"])
        if not ctx_hits:
            for k, v in base_fp.items():
                if v and (k.startswith(m["ctx"]) or m["ctx"].startswith(k)):
                    ctx_hits = v
                    break
        if ctx_hits:
            issues.append({"code": "D1", "severity": "critical",
                           "item": f"数字与基准口径不符：基准为 {'/'.join(sorted(ctx_hits))}，材料出现 {m['num']}（上下文「{m['ctx'].replace('<N>', '□')}」）",
                           "suggestion": "对照参与边界卡/简历修正为基准口径"})
        elif is_metric_shape(m["ctx"]):
            issues.append({"code": "D1", "severity": "critical",
                           "item": f"出现基准外指标数字：{m['num']}（上下文「{m['ctx'].replace('<N>', '□')}」）",
                           "suggestion": "该指标不在基准口径中，删除或改用基准数字"})
        elif float(m["num"].rstrip("%")) >= 2:
            issues.append({"code": "D1", "severity": "warn",
                           "item": f"出现基准外裸数字：{m['num']}（上下文「{m['ctx'].replace('<N>', '□')}」）",
                           "suggestion": "核对是否需与基准口径保持一致"})
    return issues


# ---------- D2 项目真实性 ----------
def extract_card_projects(card: str) -> dict[str, set[str]]:
    """从参与边界卡提取各版本专属项目名：A 版（RAG/Agent 应用类）与 B 版（推理/部署/量化类）。"""
    sets: dict[str, set[str]] = {"A": set(), "B": set()}
    zone: str | None = None
    for line in str(card or "").split("\n"):
        if re.match(r"^#{2,3}\s+二、简历 A 版", line):
            zone = "A"
        elif re.match(r"^#{2,3}\s+三、简历 B 版", line):
            zone = "B"
        elif re.match(r"^#{2,3}\s+四、", line):
            zone = None
        if not zone:
            continue
        m = re.match(r"^#{2,3}\s+(?:项目[一二三四五六七八九十\d]+[：:]?\s*)?(.+?)\s*（", line.strip())
        if m:
            sets[zone].add(m.group(1).strip())
        m2 = re.match(r"^#{2,3}\s+[\d.]+\s*项目[一二三四五六七八九十\d]+[：:]\s*(.+?)\s*（", line.strip())
        if m2:
            sets[zone].add(m2.group(1).strip())
    return sets


def extract_project_titles(md_text: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"^#{2,4}\s+([^#\n]+)$", str(md_text or ""), re.M):
        t = m.group(1).strip()
        if re.search(r"项目|系统|平台|服务化|RAG|Agent|智能体|问答|推理|量化|部署", t):
            out.append(t)
    return out


def check_project_truth(card: str, md_text: str, ver: str, file: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not card or not str(card).strip():
        return issues
    proj_sets = extract_card_projects(card)
    all_known = proj_sets["A"] | proj_sets["B"]
    for title in extract_project_titles(md_text):
        if re.match(r"^项目\d+$", title):
            continue
        if re.match(r"^项目$|项目深挖|讲述|框架|策略|总体|主线|STAR|面试|简历编号|速查|防串号|串号|【】|^##|^###|[：:—·]|^\s*[\d.]+|^[一二三四五六七八九十]+[、．.]", title):
            continue
        is_known = any(k in title or title in k for k in all_known)
        if not is_known:
            issues.append({"code": "D2", "severity": "critical",
                           "item": f"材料出现基准外项目「{title}」，参与边界卡/简历中不存在",
                           "suggestion": "删除该项目或改为基准内经历"})
            continue
        if ver == "A" and any(k in title for k in proj_sets["B"]) and not any(k in title for k in proj_sets["A"]):
            issues.append({"code": "D2", "severity": "warn",
                           "item": f"A 版材料出现 B 版专属项目「{title}」（推理/部署/量化类）",
                           "suggestion": "该项目属于简历 B 版（推理部署方向），请从 A 版材料移除或仅一句话带过"})
        if ver == "B" and any(k in title for k in proj_sets["A"]) and not any(k in title for k in proj_sets["B"]):
            issues.append({"code": "D2", "severity": "warn",
                           "item": f"B 版材料出现 A 版专属项目「{title}」（RAG/Agent 应用类）",
                           "suggestion": "该项目属于简历 A 版（应用/Agent 方向），请从 B 版材料移除或仅一句话带过"})
    return issues


# ---------- D4 结构完整性 ----------
def detect_truncation(name: str, md: str) -> list[str]:
    problems: list[str] = []
    if not md or not str(md).strip():
        return ["内容为空"]
    if "\ufffd" in md:
        problems.append("含乱码字符（输出中断残留）")
    if re.search(r"^\s*\d+[\.、)]?\s*$", md, re.M):
        problems.append("列表项仅有序号、内容缺失（输出中断）")
    if re.search(r"^\s*[-*]\s*$", md, re.M):
        problems.append("列表项空内容（输出中断）")
    if name == "05_面经分析与面试题库":
        marks = ["## 一、", "## 二、", "## 三、", "## 四、", "## 五、", "## 六、", "## 七、", "## 八、", "### 7.1", "### 7.2", "### 7.3"]
        missing = [mk for mk in marks if mk not in md]
        if missing:
            problems.append("缺少章节标记：" + "、".join(missing))
    return problems


def check_structure(name: str, md_text: str, file: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    md = str(md_text or "")
    for t in detect_truncation(name, md):
        issues.append({"code": "D4", "severity": "critical", "item": "结构异常：" + t,
                       "suggestion": "重新生成该文件"})
    m1 = re.search(r"^# [^\n]+", md, re.M)
    if m1:
        issues.append({"code": "D4", "severity": "warn",
                       "item": f"出现一级标题「{m1.group(0).strip()}」，规范要求从 ## 开始",
                       "suggestion": "降级为 ## 标题"})
    fences = md.count("```")
    if fences % 2 != 0:
        issues.append({"code": "D4", "severity": "critical",
                       "item": f"代码围栏 ``` 未配对（{fences} 个），可能破坏后续渲染",
                       "suggestion": "补齐围栏"})
    return issues


# ---------- D5 术语一致性 ----------
def check_glossary(md_text: str, file: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    md = str(md_text or "")
    for term in GLOSSARY_TERMS:
        if not re.search(r"[A-Za-z]", term):
            continue
        pattern = re.escape(term)
        exact = len(re.findall(pattern, md))
        loose = len(re.findall(pattern, md, re.I))
        if exact > 0 and loose > exact:
            issues.append({"code": "D5", "severity": "warn",
                           "item": f"术语拼写混用：材料同时存在「{term}」与其小写/变体写法（共 {loose} 处，大写 {exact} 处）",
                           "suggestion": f"统一为「{term}」"})
    return issues


# ---------- 汇总 ----------
def run_rule_check(card: str, resume_text: str, ver: str,
                   materials: list[dict[str, Any]],
                   file_names: list[str] | None = None) -> dict[str, Any]:
    """对材料执行 D1/D2/D4/D5 规则检查。

    materials: [{name, content}]（name 不含 .md 后缀）
    返回 {issues, critical, warn, ok}（ok = 无 critical）
    """
    issues: list[dict[str, Any]] = []
    base_text = "\n".join(x for x in (card, resume_text) if x)
    names = file_names or _DEFAULT_FILES
    for mat in materials:
        name = mat["name"]
        if name not in names:
            continue
        md = mat.get("content", "")
        batch: list[dict[str, Any]] = []
        batch.extend(check_digit_consistency(base_text, md, name))
        batch.extend(check_project_truth(card, md, ver, name))
        batch.extend(check_structure(name, md, name))
        batch.extend(check_glossary(md, name))
        for i in batch:
            i["file"] = name
        issues.extend(batch)
    critical = [i for i in issues if i["severity"] == "critical"]
    warn = [i for i in issues if i["severity"] == "warn"]
    return {"issues": issues, "critical": critical, "warn": warn,
            "ok": len(critical) == 0}
