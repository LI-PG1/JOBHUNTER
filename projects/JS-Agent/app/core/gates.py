"""强约束三层网关（方案 v0.5 §5）：确定性校验函数 + 错误反馈。

- Gate1 画像锚定：技能本体校验（防幻觉）+ 隐含技能复核
- Gate2 采集收录：技能匹配度（80/60/90 阈值）+ 企业类型过滤 + 时效
- Gate3 输出质检：字段完整 + 打分交叉验证 + 来源必填
"""
from __future__ import annotations

import datetime
import re
from typing import Any

from ..config import config
from ..core.enterprise import classifier
from .providers import catalog


# ---------- 通用 ----------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def today_str() -> str:
    return datetime.date.today().isoformat()


# ---------- Gate1：画像锚定 ----------

class ProfileGate:
    """画像卡强约束：技能必须能在技能本体中找到（防幻觉）；推断技能标记待复核。"""

    # 技能本体中归属推理线的技能 id（用于隐含技能补全复核）
    INFERENCE_SKILL_IDS = {
        "vllm", "tensorrt", "sglang", "quantization", "inference-optimization",
        "onnx-openvino", "cuda-gpu", "distributed-training",
    }

    def validate(self, card: dict[str, Any], raw_text: str) -> dict[str, Any]:
        """校验画像卡，返回 {ok, errors[], warnings[], card}。"""
        errors: list[str] = []
        warnings: list[str] = []
        skills = card.get("skills")
        if not isinstance(skills, list) or not skills:
            errors.append("画像卡缺少技能列表")
        else:
            valid: list[dict[str, Any]] = []
            for s in skills:
                name = str(s.get("name", "")).strip()
                if not name:
                    continue
                # 防幻觉：技能名必须命中本体（名称或别名）
                hit = catalog.match_skills(name)
                if hit:
                    valid.append(s)
                else:
                    warnings.append(f"技能「{name}」未命中技能本体，已忽略")
            card["skills"] = valid
            if not valid:
                errors.append("画像卡无有效技能")

        required = ["education", "grad_year", "city"]
        for f in required:
            if not str(card.get(f, "")).strip():
                errors.append(f"画像卡缺少必填字段 {f}")
        # 经验年限可空（方案 v0.5：可选项）
        if "experience_years" not in card:
            card["experience_years"] = None
        # 企业类型：仅保留 LLM 从画像文本明确推断出的类型；未声明 → 空（不过滤，
        # 由前端多选兜底）。不给「全部 5 类」默认值，否则会稀释前端勾选的硬约束。
        if "company_types" not in card or not isinstance(card["company_types"], list):
            card["company_types"] = []

        return {"ok": not errors, "errors": errors, "warnings": warnings, "card": card}

    def implicit_skills(self, card: dict[str, Any], raw_text: str) -> list[str]:
        """从画像推断的隐含技能中筛出『与推理线强相关』的技能（LLM 已标 confirmed=false）。

        规则复核：若推断技能命中本体且属于推理线（含 both），返回技能名，供收录 Gate 加分。
        """
        result: list[str] = []
        for s in card.get("skills", []):
            if s.get("confirmed") is True:
                continue
            name = str(s.get("name", "")).strip()
            hit = catalog.match_skills(name)
            if hit:
                skill = hit[0]["skill"]
                if skill.get("line") in ("inference", "both") or skill["id"] in self.INFERENCE_SKILL_IDS:
                    result.append(skill["name"])
        return result


profile_gate = ProfileGate()


# ---------- Gate2：采集收录 ----------

class CollectionGate:
    """岗位收录判定：技能匹配度 + 企业类型 + 时效 + 地域。"""

    @staticmethod
    def _profile_ids(profile_skills: list[str], implicit: list[str] | None = None) -> set[str]:
        """画像技能（含推断）→ 本体技能 id 集合（按别名/名称命中本体）。"""
        ids: set[str] = set()
        for name in list(profile_skills) + list(implicit or []):
            for h in catalog.match_skills(name):
                ids.add(h["skill"]["id"])
        return ids

    def match_score(
        self,
        profile_skills: list[str],
        jd_text: str,
        implicit: list[str] | None = None,
    ) -> tuple[float, list[str], list[str]]:
        """计算技能匹配度（0-100）：按本体技能 id 匹配（避免名称差异失配）。

        分子 = 画像技能（含推断隐含技能）中命中 JD 的技能数；分母 = JD 中出现的核心技能数（去重）。
        返回 (score, matched_skill_names, jd_skill_names)。
        """
        hits = catalog.match_skills(jd_text or "")
        jd_ids = [h["skill"]["id"] for h in hits]
        jd_skills = [h["skill"]["name"] for h in hits]
        if not jd_ids:
            return 0.0, [], []
        profile_ids = self._profile_ids(profile_skills, implicit)
        matched = [name for name, sid in zip(jd_skills, jd_ids) if sid in profile_ids]
        return round(100.0 * len(matched) / len(jd_ids), 1), matched, jd_skills

    def judge(
        self,
        entry: dict[str, Any],
        profile_skills: list[str],
        profile_implicit: list[str],
        selected_types: list[str],
    ) -> dict[str, Any]:
        """收录判定，返回加入 status/gap 的 entry。"""
        # 匹配打分与缺失技能用同一组 profile_ids（隐含技能参与打分，保持口径一致）
        hits = catalog.match_skills(entry.get("jd_text", ""))
        jd_ids = [h["skill"]["id"] for h in hits]
        jd_skills = [h["skill"]["name"] for h in hits]
        profile_ids = self._profile_ids(profile_skills, profile_implicit)
        matched = [name for name, sid in zip(jd_skills, jd_ids) if sid in profile_ids]
        score = round(100.0 * len(matched) / len(jd_ids), 1) if jd_ids else 0.0
        missing = [name for name, sid in zip(jd_skills, jd_ids) if sid not in profile_ids]

        # 企业类型过滤（前端多选 ∪ 画像推断）。「未知」不再豁免：
        # 无法归类的岗位按不在所选范围处理，避免漏网混入用户未选类型。
        # selected_types 为空（前端全不勾 + 画像未声明）→ 不限，不过滤。
        etype = entry.get("enterprise_type", "未知")
        if selected_types and etype not in selected_types:
            entry["status"] = "excluded"
            entry["exclude_reason"] = f"企业类型 {etype} 不在所选范围"
            return entry

        # 时效过滤（updated_at 距今 ≤ fresh_days）
        fresh_days = config.constraints["fresh_days"]
        upd = entry.get("updated_at", "")
        if upd and re.match(r"\d{4}-\d{2}-\d{2}", upd):
            try:
                upd_d = datetime.date.fromisoformat(upd[:10])
                if (datetime.date.today() - upd_d).days > fresh_days:
                    entry["status"] = "excluded"
                    entry["exclude_reason"] = f"已超过时效（{fresh_days} 天）：{upd}"
                    return entry
            except ValueError:
                pass

        entry["match_score"] = score
        entry["matched_skills"] = matched
        entry["missing_skills"] = missing

        accept = config.constraints["match_accept"]
        gap = config.constraints["match_gap"]
        if score >= accept:
            entry["status"] = "accepted"
        elif score >= gap:
            entry["status"] = "gap"
            entry["gap_tips"] = f"匹配度 {score}%（<{accept}%），需补足技能：{'、'.join(missing[:5]) or '无'}"
        else:
            entry["status"] = "excluded"
            entry["exclude_reason"] = f"匹配度 {score}% 低于 {gap}% 阈值"
        return entry


def profile_set(profile_skills: list[str], implicit: list[str]) -> set[str]:
    return set(profile_skills) | set(implicit)


collection_gate = CollectionGate()


# ---------- Gate3：输出质检 ----------

class OutputGate:
    """清单输出质检：字段完整 + 来源必填 + 技能线一致 + 打分与规则交叉验证。

    company 不作必填：搜索器模式下摘要常提取不到真实雇主（洗涤已尽力），
    缺失只降低展示完整度，不阻断收录（防编造靠 source_url 硬校验）。
    """

    REQUIRED_FIELDS = ["title", "match_score", "skill_line", "missing_skills", "source_url"]

    def validate_job(self, job: dict[str, Any]) -> list[str]:
        errors = []
        for f in self.REQUIRED_FIELDS:
            v = job.get(f)
            # 列表字段（missing_skills）允许为空 list（100% 匹配是合法状态），其余字段不得为空
            if v is None or v == "" or (f == "missing_skills" and not isinstance(v, list)):
                errors.append(f"缺少字段 {f}")
        if not str(job.get("source_url", "")).startswith("http"):
            errors.append("source_url 非法：无来源链接的岗位禁止输出（防编造）")
        return errors

    def cross_check(self, job: dict[str, Any], rule_score: float, final_score: float | None = None) -> list[str]:
        """LLM 打分 vs 规则打分交叉验证（混合判定双护栏，改造设计 §2.5）：
        |LLM−规则|>15 报错（沿用）；|final−规则|>25 报错（混合判定合并分护栏）。"""
        errors = []
        llm_score = job.get("match_score")
        if isinstance(llm_score, (int, float)) and rule_score is not None:
            if abs(float(llm_score) - float(rule_score)) > 15:
                errors.append(f"打分交叉验证偏差过大：LLM={llm_score} vs 规则={rule_score}")
        if final_score is not None and rule_score is not None:
            if abs(float(final_score) - float(rule_score)) > 25:
                errors.append(f"最终分交叉验证偏差过大：final={final_score} vs 规则={rule_score}")
        return errors


output_gate = OutputGate()
