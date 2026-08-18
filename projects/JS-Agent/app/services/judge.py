"""混合判定服务（改造设计 §2）：硬约束层 + 规则技能分 + LLM 软性判定 + 合并仲裁。

核心原则（规则否决制）：
1. 硬约束永远是硬约束（企业档/时效/地域/学历/必填技能）——不过即淘汰，LLM 无权翻案；
2. LLM 只能「锦上添花」：final = w_rule*rule + w_llm*llm（默认 0.6/0.4）；
3. 失败降级：LLM 抛错 / 无证据 → LLM 权重归零，退回纯规则分（行为 ≈ 改造前）。

对外入口：
- judge(entry, card, profile_skills, implicit, selected_types, llm_verdict=None)  单条门面（loop 浅判/深判/扩散判统一走这里）
- hard_check / rule_score / llm_judge_batch / merge / finalize  分段能力（批量路径由调用方组装）
"""
from __future__ import annotations

import datetime
import json
import re
from typing import Any

from ..agent.prompts import JUDGE_SYSTEM
from ..config import config
from ..core.errors import JSAgentError
from ..core.gates import collection_gate
from ..core.llm import llm
from ..core.providers import catalog

# 学历级别（仅用于「JD 要求高于画像」判定）
_EDU_LEVEL = {"博士": 3, "硕士": 2, "本科": 1}

_DIM_WEIGHTS = {"jd_fit": 0.4, "job_quality": 0.3, "growth": 0.3}


def _edu_level(text: str) -> int:
    for k, v in _EDU_LEVEL.items():
        if k in text:
            return v
    return 0


def hard_check(
    entry: dict[str, Any],
    card: dict[str, Any],
    profile_skills: list[str],
    implicit: list[str],
    selected_types: list[str],
) -> dict[str, Any]:
    """硬约束层：企业档 / 时效 / 地域 / 学历 / 必填技能。返回 HardResult。

    地域/学历/必填技能按 config.judge 开关启用（默认开）；关闭即回到改造前的「企业+时效」行为。
    """
    veto: list[str] = []
    warnings: list[str] = []
    j = config.judge

    # 1) 企业类型（前端多选 ∪ 画像推断）；「未知」不再豁免
    etype = entry.get("enterprise_type", "未知")
    if selected_types and etype not in selected_types:
        veto.append(f"企业类型 {etype} 不在所选范围")

    # 2) 时效（updated_at 距今 ≤ fresh_days；无日期放行但提示风险）
    fresh_days = config.constraints["fresh_days"]
    upd = entry.get("updated_at", "")
    if upd and re.match(r"\d{4}-\d{2}-\d{2}", upd):
        try:
            d = datetime.date.fromisoformat(upd[:10])
            if (datetime.date.today() - d).days > fresh_days:
                veto.append(f"已超过时效（{fresh_days} 天）：{upd}")
        except ValueError:
            pass
    elif not upd:
        warnings.append("岗位无更新日期，时效风险未知")

    # 3) 地域（画像明确 vs 岗位明确且不一致 → 淘汰；岗位未知 → 放行降权）
    if j.get("hard_city", True):
        card_city = str(card.get("city") or "").strip()
        e_city = str(entry.get("city") or "").strip()
        if card_city and e_city and card_city not in e_city and e_city not in card_city:
            veto.append(f"地域不符：画像 {card_city} vs 岗位 {e_city}")
        elif card_city and not e_city:
            warnings.append("岗位城市未知，按放行处理")

    # 4) 学历（画像级别 < JD 明确要求级别 → 淘汰；JD 未知/不限 → 放行）
    if j.get("hard_degree", True):
        card_lv = _edu_level(str(card.get("education") or ""))
        jd_lv = _edu_level(str(entry.get("degree") or ""))
        if jd_lv and card_lv and jd_lv > card_lv:
            veto.append(f"学历不符：画像 {card.get('education')}，岗位要求 {entry.get('degree')}")

    # 5) 必填技能（画像 confirmed 核心技能前 N 个在 JD 全部缺失 → 一票否决）
    if j.get("hard_required_skills", True):
        top = j.get("required_skill_top", 3)
        confirmed = [s["name"] for s in card.get("skills", []) if s.get("confirmed") is True][:top]
        jd_ids = {h["skill"]["id"] for h in catalog.match_skills(entry.get("jd_text") or "")}
        req_ids: set[str] = set()
        for name in confirmed:
            for h in catalog.match_skills(name):
                req_ids.add(h["skill"]["id"])
        if req_ids and not (req_ids & jd_ids):
            veto.append(f"缺核心技能（一票否决）：{'、'.join(confirmed)}")

    # 规则技能分（与 Gate2 同一口径）
    score, matched, jd_skills = collection_gate.match_score(profile_skills, entry.get("jd_text") or "", implicit)
    missing = [name for name in jd_skills if name not in matched]

    return {
        "passed": not veto,
        "veto_reasons": veto,
        "warnings": warnings,
        "rule_score": score,
        "matched_skills": matched,
        "missing_skills": missing,
    }


def rule_score(profile_skills: list[str], jd_text: str, implicit: list[str] | None = None) -> tuple[float, list[str], list[str]]:
    """规则技能分（0-100），与 gates.CollectionGate.match_score 同口径。"""
    return collection_gate.match_score(profile_skills, jd_text, implicit)


def _judge_user(entries: list[dict[str, Any]], card: dict[str, Any]) -> str:
    """软性判定输入：画像卡摘要 + 岗位条目精简（jd_text ≤ 300 字，避免 token 爆炸）。"""
    card_sum = {
        "city": card.get("city"), "education": card.get("education"),
        "skills": [s["name"] for s in card.get("skills", [])],
        "raw_summary": (card.get("raw_summary") or "")[:200],
    }
    items = [{
        "index": i,
        "title": e.get("title", ""), "company": e.get("company", ""),
        "city": e.get("city", ""), "salary": e.get("salary", ""),
        "degree": e.get("degree", ""), "experience": e.get("experience", ""),
        "skill_line": e.get("skill_line", ""),
        "jd_text": (e.get("jd_text") or "")[:300],
        "rule_score": e.get("match_score", 0),
    } for i, e in enumerate(entries)]
    return f"画像卡：\n{json.dumps(card_sum, ensure_ascii=False)}\n\n候选岗位：\n{json.dumps(items, ensure_ascii=False)}"


def _weighted_score(dims: dict[str, Any]) -> float:
    """三个维度加权软性分（缺失维度按 50 计，与 prompt「信息不足给 50」一致）。"""
    total_w = 0.0
    acc = 0.0
    for dim, w in _DIM_WEIGHTS.items():
        d = dims.get(dim) or {}
        try:
            s = float(d.get("score", 50))
        except (TypeError, ValueError):
            s = 50.0
        s = max(0.0, min(100.0, s))
        acc += w * s
        total_w += w
    return round(acc / total_w, 1) if total_w else 50.0


def llm_judge_batch(
    entries: list[dict[str, Any]],
    card: dict[str, Any],
    provider_id: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """对硬约束通过条目批量软性判定。返回 {source_url: LLMVerdict}。

    - 按 batch_size 分批（默认 20 条/批）；
    - LLM 抛错 → 该批降级（跳过，调用方按纯规则）；
    - evidence_ok：批内任一维度/overall 引用了原文才算有证据，否则该批权重归零。
    """
    if not entries:
        return {}
    j = config.judge
    batch = int(j.get("batch_size", 20))
    out: dict[str, Any] = {}
    for start in range(0, len(entries), batch):
        chunk = entries[start:start + batch]
        try:
            obj, _ = llm.chat_json(JUDGE_SYSTEM, _judge_user(chunk, card), provider_id, model, max_tokens=4000)
        except JSAgentError:
            continue  # 该批降级：纯规则
        verdicts = obj.get("verdicts") if isinstance(obj, dict) else None
        if not isinstance(verdicts, list):
            continue
        evidence_ok = any(
            (v.get("dimensions") or {}).get(d, {}).get("evidence", "") or (v.get("overall") or {}).get("reason", "")
            for v in verdicts if isinstance(v, dict)
            for d in ("jd_fit", "job_quality", "growth")
        )
        for i, v in enumerate(verdicts):
            if not isinstance(v, dict) or i >= len(chunk):
                continue
            dims = v.get("dimensions") or {}
            key = chunk[i].get("source_url") or chunk[i].get("title", "")
            out[key] = {
                "llm_score": _weighted_score(dims),
                "dimensions": dims,
                "overall_reason": (v.get("overall") or {}).get("reason", ""),
                "red_flags": v.get("red_flags", []) if isinstance(v.get("red_flags"), list) else [],
                "resume_tips": v.get("resume_tips", []) if isinstance(v.get("resume_tips"), list) else [],
                "evidence_ok": bool(evidence_ok),
            }
    return out


def merge(rule_score: float, llm_verdict: dict[str, Any] | None) -> tuple[float, list[str]]:
    """合并分 + 仲裁（改造设计 §2.5）：

    - LLM 缺失 / 无证据 → final = rule（权重归零，退回纯规则）
    - LLM 大幅看空（llm < rule-30）且无 red_flags → 保守取 min(rule, llm)
    - LLM 大幅看多（llm > rule+20）且 rule < gap → 封顶在 gap（不能抬进 accepted）
    """
    j = config.judge
    if not llm_verdict:
        return round(rule_score, 1), []
    if not llm_verdict.get("evidence_ok"):
        return round(rule_score, 1), ["llm_evidence_missing"]
    w = j.get("weights", {"rule": 0.6, "llm": 0.4})
    llm_score = llm_verdict.get("llm_score", 50.0)
    down = float(j.get("llm_downgrade_cap", 30))
    up = float(j.get("llm_upgrade_floor", 20))
    flags: list[str] = []
    if llm_score < rule_score - down and not llm_verdict.get("red_flags"):
        # 看空无证据支撑 → 保守取值（取较小者即 min）
        llm_score = min(rule_score, llm_score)
        flags.append("llm_downgrade_capped")
    final = w["rule"] * rule_score + w["llm"] * llm_score
    if llm_score > rule_score + up:
        gap = float(config.constraints["match_gap"])
        if rule_score < gap:
            final = min(final, gap)
            flags.append("llm_upgrade_floored")
    return round(final, 1), flags


def finalize(entry: dict[str, Any], hard: dict[str, Any], llm_verdict: dict[str, Any] | None) -> dict[str, Any]:
    """落判定：final_score + status（阈值沿用 match_accept/match_gap）。"""
    final, flags = merge(hard["rule_score"], llm_verdict)
    entry["final_score"] = final
    entry["match_score"] = hard["rule_score"]  # 保留规则分供 Gate3 交叉验证
    if llm_verdict:
        entry["llm_verdict"] = {**llm_verdict, "_flags": flags}
    entry["_warnings"] = hard["warnings"]
    accept = float(config.constraints["match_accept"])
    gap = float(config.constraints["match_gap"])
    if final >= accept:
        entry["status"] = "accepted"
    elif final >= gap:
        entry["status"] = "gap"
        entry["gap_tips"] = f"匹配度 {final}%（<{accept}%），需补足技能：{'、'.join(hard['missing_skills'][:5]) or '无'}"
    else:
        entry["status"] = "excluded"
        entry["exclude_reason"] = f"匹配度 {final}% 低于 {gap}% 阈值"
    return entry


def judge(
    entry: dict[str, Any],
    card: dict[str, Any],
    profile_skills: list[str],
    implicit: list[str],
    selected_types: list[str],
    llm_verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """单条门面：hard_check → rule_score →（可选）LLM → merge → finalize。

    调用方可传入 llm_verdict（批量路径预取）；不传且 llm_enabled 时内部单条判定。
    """
    hard = hard_check(entry, card, profile_skills, implicit, selected_types)
    if not hard["passed"]:
        entry["status"] = "excluded"
        entry["exclude_reason"] = "；".join(hard["veto_reasons"])
        entry["match_score"] = hard["rule_score"]
        entry["matched_skills"] = hard["matched_skills"]
        entry["missing_skills"] = hard["missing_skills"]
        return entry
    entry["match_score"] = hard["rule_score"]
    entry["matched_skills"] = hard["matched_skills"]
    entry["missing_skills"] = hard["missing_skills"]
    if llm_verdict is None and config.judge.get("llm_enabled", True):
        key = entry.get("source_url") or entry.get("title", "")
        llm_verdict = llm_judge_batch([entry], card).get(key)
    return finalize(entry, hard, llm_verdict)


def judge_batch(
    entries: list[dict[str, Any]],
    card: dict[str, Any],
    profile_skills: list[str],
    implicit: list[str],
    selected_types: list[str],
    provider_id: str | None = None,
    model: str | None = None,
    llm_enabled: bool | None = None,
) -> list[dict[str, Any]]:
    """批量门面（loop 主路径）：硬约束过滤 →（启用时）批量 LLM 判定 → 逐条 finalize。

    与单条 judge 结果等价，但 LLM 调用从「每条一次」降为「每批一次」。
    llm_enabled=None 时取 config.judge.llm_enabled（请求级覆盖 judge_llm 时传入显式值）。
    """
    if llm_enabled is None:
        llm_enabled = config.judge.get("llm_enabled", True)
    passed: list[dict[str, Any]] = []
    for e in entries:
        h = hard_check(e, card, profile_skills, implicit, selected_types)
        e["_hard"] = h
        e["match_score"] = h["rule_score"]
        e["matched_skills"] = h["matched_skills"]
        e["missing_skills"] = h["missing_skills"]
        if h["passed"]:
            passed.append(e)
    verdicts: dict[str, Any] = {}
    if passed and llm_enabled:
        verdicts = llm_judge_batch(passed, card, provider_id, model)
    for e in entries:
        h = e.pop("_hard")
        if h["passed"]:
            finalize(e, h, verdicts.get(e.get("source_url") or e.get("title", "")))
        else:
            e["status"] = "excluded"
            e["exclude_reason"] = "；".join(h["veto_reasons"])
    return entries


judge_service = judge
