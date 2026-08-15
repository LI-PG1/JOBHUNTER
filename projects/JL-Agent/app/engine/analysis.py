"""JD 分析引擎（契约 §5.2/§3.1.6）：JD → 共享事实表 + 领域标签 + 主题一致性。

P3 落地：
- analyze(): 调用 LLM 提炼方向/核心技能/JD 诉求/项目类型/量化风格/领域标签 → 构建 Factsheet，
  并把领域标签写回每套 Job（作为后续主题一致性的事实源）。
- check_theme(): 领域标签共享 ≥1 直接通过；否则 LLM 语义兜底（≥0.4 通过），
  跨领域 → E_THEME_BLOCK 40003。
"""
import json
import re
from typing import List, Optional

from ..core.errors import AppError, E_LLM, E_PARAM, E_THEME_BLOCK
from ..core.rules import RulesLoader
from ..core.providers import LLMProvider
from ..schemas import Factsheet, Job, Resume
from ..core.validation import project_count_for
from .prompts import jd_analysis_messages, theme_check_messages

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(content: str) -> dict:
    """从 LLM 输出中提取 JSON 对象（容忍 ```json 围栏与前后解释文本）。"""
    m = _FENCE_RE.search(content)
    if m:
        content = m.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end <= start:
        raise AppError(E_LLM, "LLM 输出缺少 JSON 结构")
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AppError(E_LLM, f"LLM 输出 JSON 解析失败: {exc}") from exc


def clamp_score(value, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


class JDAnalyzer:
    """JD 分析 + 主题一致性（单任务串行环境，无状态，可复用）。"""

    def __init__(self, provider: LLMProvider, rules: RulesLoader):
        self.provider = provider
        self.rules = rules

    # ------------------------------------------------------------ JD 分析 → 事实表

    async def analyze(
        self,
        jobs: List[Job],
        resume: Resume,
        page_option: str = "one-page",
        deep_search: bool = False,
    ) -> Factsheet:
        """JD 分析 → 共享事实表；领域标签写回各 Job；计算 keywordCoverage。"""
        if not jobs:
            raise AppError(E_PARAM, "请至少填写 1 套目标岗位 JD")

        industry = self._match_industry(jobs)
        jobs_rules = self.rules.jobs_rules()
        messages = jd_analysis_messages(
            [j.model_dump(by_alias=True) for j in jobs],
            {**(industry or {}), "jobs": jobs_rules},
            {"identity": resume.identity.value, "pageOption": page_option, "deepSearch": deep_search},
        )
        content = await self.provider.chat(messages, json_mode=True, max_tokens=2048, temperature=0.3)
        parsed = extract_json(content)

        domain_tags = _string_list(parsed.get("domainTags"))
        core_skills = _string_list(parsed.get("coreSkills"))
        direction = str(parsed.get("direction") or "未识别方向").strip()[:64]

        # 领域标签写回每套 JD（同一职业方向，标签共享）
        for job in jobs:
            job.domain_tags = domain_tags

        internship_count = len(resume.internship)
        factsheet = Factsheet(
            direction=direction,
            identity=resume.identity.value,
            page_option=page_option,
            core_skills=core_skills,
            jd_focus=str(parsed.get("jdFocus") or "").strip(),
            project_type=str(parsed.get("projectType") or "").strip(),
            metric_style=str(parsed.get("metricStyle") or "").strip(),
            quantity={"internshipCount": internship_count,
                      "projectCount": project_count_for(page_option, internship_count)},
            keyword_coverage=self._keyword_coverage(resume, core_skills),
        )
        return factsheet

    def _match_industry(self, jobs: List[Job]) -> Optional[dict]:
        """按 JD 文本关键词命中率挑选行业规则（无命中返回 None，走通用分析）。"""
        jd_text = " ".join(f"{j.title} {j.jd_text}" for j in jobs).lower()
        best, best_score = None, 0
        for payload in self.rules.industries().values():
            score = sum(1 for kw in payload.get("keywords", []) if kw.lower() in jd_text)
            if score > best_score:
                best, best_score = payload, score
        return best

    def _keyword_coverage(self, resume: Resume, core_skills: List[str]) -> float:
        """用户技能/项目技术栈对 JD 核心技能的覆盖率（契约 §5.2 keywordCoverage）。"""
        pool = [s.name for s in resume.skill]
        for p in resume.project:
            pool.append(p.name)
            pool.extend(p.tech_stack or [])
        pool_text = " ".join(pool).lower()
        if not core_skills:
            return 0.0
        hits = sum(1 for k in core_skills if k and k.lower() in pool_text)
        return round(hits / len(core_skills), 2)

    # ------------------------------------------------------------ 主题一致性（§3.1.6）

    async def check_theme(self, resume: Resume, jobs: List[Job]) -> None:
        """领域标签共享 ≥1 通过；否则语义兜底 ≥0.4 通过；均不满足 → 40003 拦截。"""
        jd_tags = sorted({t for j in jobs for t in (j.domain_tags or [])})
        resume_tags = self._resume_tags(resume)

        if not jd_tags or not resume_tags:
            return  # 任一为空无法判定，不拦截（避免死路）

        shared = set(jd_tags) & set(resume_tags)
        if shared:
            return

        threshold = float(self.rules.jobs_rules().get("semantic_fallback_threshold", 0.4))
        content = await self.provider.chat(
            theme_check_messages(jd_tags, resume_tags, threshold),
            json_mode=True,
            max_tokens=512,
            temperature=0.2,
        )
        parsed = extract_json(content)
        score = clamp_score(parsed.get("score"))
        if score >= threshold:
            return
        raise AppError(
            E_THEME_BLOCK,
            "目标岗位领域与您的经历方向不一致，建议补充相关项目/技能后重试",
            {"score": score, "jdTags": jd_tags, "resumeTags": resume_tags},
        )

    def _resume_tags(self, resume: Resume) -> List[str]:
        """从技能/项目/实习文本中匹配行业规则关键词，作为简历领域标签。"""
        pool: List[str] = [s.name for s in resume.skill]
        for p in resume.project:
            pool.append(p.name)
            pool.extend(p.tech_stack or [])
        for it in resume.internship:
            pool.extend([it.company, it.position])
            for d in it.duties:
                pool.append(d.text)
        tags = set()
        pool_lower = [t.lower() for t in pool]
        for payload in self.rules.industries().values():
            for kw in payload.get("keywords", []):
                if any(kw.lower() in t for t in pool_lower):
                    tags.add(kw)
        return sorted(tags)


def _string_list(value) -> List[str]:
    """容错转字符串列表（LLM 可能返回空/None/非列表）。"""
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x).strip()[:64] for x in value if str(x).strip()]
    return []
