"""规则库加载器：加载 + Schema 校验 + 索引构建。

规则库是 JS-Agent 的核心资产，启动时统一加载一次：
- skills.json     技能本体（含 aliases/keywords 全量小写索引）
- roles.json      岗位本体（按 role_id 索引）
- industries.json 行业本体（按 id 索引）
- jobs/*.json     种子岗位库（合并）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import config
from ..core.errors import RulesError

# 技能线中文显示映射
LINE_LABEL = {
    "application": "应用",
    "inference": "推理",
    "both": "双线",
    "core": "基础",
}


class RuleCatalog:
    """规则库目录：加载后只读访问。"""

    def __init__(self, rules_dir: Path | None = None) -> None:
        self.rules_dir = rules_dir or config.rules_dir
        self.skills: list[dict] = []
        self.roles: list[dict] = []
        self.industries: list[dict] = []
        self.jobs: list[dict] = []
        # 索引
        self.skill_by_id: dict[str, dict] = {}
        self.role_by_id: dict[str, dict] = {}
        self.industry_by_id: dict[str, dict] = {}
        # 文本匹配索引：小写关键词/别名 → skill_id
        self.skill_term_index: list[tuple[str, str]] = []  # (term_lower, skill_id)
        self.role_term_index: list[tuple[str, str]] = []  # (term_lower, role_id)
        self._load_all()

    # ---------- 加载 ----------

    def _load_all(self) -> None:
        if not self.rules_dir.exists():
            raise RulesError(f"规则库目录不存在: {self.rules_dir}")
        self.skills = self._load_json("skills.json", schema="skills.schema.json", key="skills")
        self.roles = self._load_json("roles.json", schema="roles.schema.json", key="roles")
        self.industries = self._load_json("industries.json", schema="industries.schema.json", key="industries")
        self.jobs = self._load_jobs()
        self._build_index()

    def _load_json(self, name: str, schema: str, key: str) -> list:
        path = self.rules_dir / name
        if not path.exists():
            raise RulesError(f"规则文件缺失: {path.name}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RulesError(f"规则文件解析失败 {path.name}: {exc}") from exc
        items = data.get(key)
        if not isinstance(items, list) or not items:
            raise RulesError(f"规则文件内容异常 {path.name}: 缺少 {key} 列表")
        self._validate_schema(path, schema, data)
        return items

    def _validate_schema(self, path: Path, schema_name: str, data: dict) -> None:
        """Schema 校验（jsonschema），校验失败仅告警不阻断（兼容自定义扩展）。"""
        try:
            import jsonschema
        except ImportError:
            return
        schema_path = self.rules_dir / "schema" / schema_name
        if not schema_path.exists():
            return
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(data, schema)
        except (jsonschema.ValidationError, json.JSONDecodeError, OSError) as exc:
            raise RulesError(f"规则 Schema 校验失败 {path.name}: {exc}") from exc

    def _load_jobs(self) -> list[dict]:
        jobs_dir = self.rules_dir / "jobs"
        jobs: list[dict] = []
        if not jobs_dir.exists():
            return jobs
        for path in sorted(jobs_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise RulesError(f"岗位库解析失败 {path.name}: {exc}") from exc
            items = data.get("jobs", [])
            for item in items:
                item["_city"] = data.get("city", "")
            jobs.extend(items)
        return jobs

    # ---------- 索引 ----------

    def _build_index(self) -> None:
        for s in self.skills:
            self.skill_by_id[s["id"]] = s
            self._add_terms(self.skill_term_index, s, s.get("aliases", []), s.get("keywords", []), s["id"])
        for r in self.roles:
            self.role_by_id[r["id"]] = r
            self._add_terms(self.role_term_index, r, r.get("aliases", []), [r["name"]], r["id"])
        for ind in self.industries:
            self.industry_by_id[ind["id"]] = ind

    @staticmethod
    def _add_terms(index: list[tuple[str, str]], obj: dict, aliases: list, keywords: list, ref_id: str) -> None:
        terms = set()
        terms.add(obj["name"].lower())
        terms.update(str(a).lower() for a in aliases)
        terms.update(str(k).lower() for k in keywords)
        for t in terms:
            if t:
                index.append((t, ref_id))

    # ---------- 文本匹配 ----------

    @staticmethod
    def _norm(text: str) -> str:
        """小写 + 归一化空白（中文无需分词，直接子串匹配）。"""
        return re.sub(r"\s+", " ", text.lower()).strip()

    _ASCII_TERM = re.compile(r"^[a-z0-9][a-z0-9 .\-_/+]*$")

    @classmethod
    def _term_hit(cls, term: str, norm: str) -> bool:
        """术语命中判定：纯 ASCII 词条用词边界匹配（避免 "llm" 误命中 "vllm"），其余子串匹配。"""
        if not term:
            return False
        if cls._ASCII_TERM.match(term):
            return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", norm) is not None
        return term in norm

    def match_skills(self, text: str) -> list[dict]:
        """在文本中命中技能，返回 [{skill, matched_term}]（按 term 长度降序，避免短词先命中）。"""
        norm = self._norm(text)
        if not norm:
            return []
        hits: dict[str, str] = {}
        for term, skill_id in self.skill_term_index:
            if len(term) >= 2 and self._term_hit(term, norm):
                # 保留最长匹配
                if skill_id not in hits or len(term) > len(hits[skill_id]):
                    hits[skill_id] = term
        return [{"skill": self.skill_by_id[sid], "matched_term": term} for sid, term in hits.items()]

    def match_role(self, text: str) -> dict | None:
        """在文本（岗位标题/JD）中命中岗位本体，返回 role 或 None。"""
        norm = self._norm(text)
        if not norm:
            return None
        best: tuple[int, str] | None = None
        for term, role_id in self.role_term_index:
            if len(term) >= 2 and term in norm:
                if best is None or len(term) > best[0]:
                    best = (len(term), role_id)
        if best is None:
            return None
        return self.role_by_id[best[1]]

    def match_industry(self, text: str) -> dict | None:
        """在文本（公司/JD）中命中行业本体。"""
        norm = self._norm(text)
        if not norm:
            return None
        best: tuple[int, str] | None = None
        for ind in self.industries:
            terms = [ind["name"]] + ind.get("keywords", []) + ind.get("companies", [])
            for t in terms:
                tl = str(t).lower()
                if len(tl) >= 2 and tl in norm:
                    if best is None or len(tl) > best[0]:
                        best = (len(tl), ind["id"])
        if best is None:
            return None
        return self.industry_by_id[best[1]]

    def line_label(self, line: str) -> str:
        return LINE_LABEL.get(line, line)


catalog = RuleCatalog()
