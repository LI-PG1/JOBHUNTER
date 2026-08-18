"""混合判定服务单元测试（改造设计 §2）：硬约束 / 规则技能分 / LLM 合并仲裁 / 批量门面。

LLM 层通过 monkeypatch app.core.llm.llm.chat_json 注入确定性输出，不依赖网络/真实 Key。
"""
from __future__ import annotations

import datetime
from typing import Any

from app.core.errors import JSAgentError
from app.services.judge import hard_check, judge_batch, merge, finalize

CARD = {
    "skills": [
        {"name": "vLLM", "line": "inference", "confirmed": True},
        {"name": "RAG", "line": "application", "confirmed": True},
        {"name": "量化", "line": "inference", "confirmed": False},  # 推断技能
    ],
    "education": "硕士",
    "grad_year": "2027",
    "city": "深圳",
    "experience_years": None,
}

TODAY = datetime.date.today().isoformat()


def _entry(**kw: Any) -> dict[str, Any]:
    base = {
        "title": "AI 应用开发工程师", "company": "示例科技", "city": "深圳",
        "jd_text": "使用 vLLM 部署服务，负责 RAG 问答系统", "degree": "本科",
        "updated_at": TODAY, "enterprise_type": "大型", "is_job": True,
    }
    base.update(kw)
    return base


def _verdict(llm_score: float, *, evidence: bool = True, red_flags: list | None = None) -> dict[str, Any]:
    """构造 LLMVerdict：证据引用原文 → evidence_ok=True。"""
    return {
        "llm_score": llm_score,
        "dimensions": {"jd_fit": {"score": llm_score, "evidence": "使用 vLLM 部署服务"},
                       "job_quality": {"score": 60, "evidence": "JD 完整"},
                       "growth": {"score": 60, "evidence": "方向契合"}},
        "overall_reason": "方向契合度较高",
        "red_flags": red_flags or [],
        "resume_tips": ["补充 RAG 项目细节"],
        "evidence_ok": evidence,
    }


# ---------- 硬约束层 ----------

def test_hard_check_passes_full_match():
    h = hard_check(_entry(), CARD, ["vLLM", "RAG"], [], [])
    assert h["passed"] is True
    assert h["rule_score"] == 100.0
    assert not h["veto_reasons"]


def test_hard_check_veto_enterprise_type():
    h = hard_check(_entry(enterprise_type="央企"), CARD, ["vLLM", "RAG"], [], ["大型"])
    assert h["passed"] is False
    assert any("企业类型" in r for r in h["veto_reasons"])


def test_hard_check_veto_city_mismatch():
    h = hard_check(_entry(city="北京"), CARD, ["vLLM", "RAG"], [], [])
    assert h["passed"] is False
    assert any("地域不符" in r for r in h["veto_reasons"])


def test_hard_check_veto_degree_higher_than_profile():
    # 画像硕士，JD 要求博士 → 淘汰
    h = hard_check(_entry(degree="博士"), CARD, ["vLLM", "RAG"], [], [])
    assert h["passed"] is False
    assert any("学历不符" in r for r in h["veto_reasons"])


def test_hard_check_veto_required_skill_missing():
    # confirmed 核心技能（vLLM/RAG）在 JD 中完全缺失 → 一票否决
    h = hard_check(_entry(jd_text="负责推荐系统与数据挖掘，无大模型技能"), CARD, ["vLLM", "RAG"], [], [])
    assert h["passed"] is False
    assert any("缺核心技能" in r for r in h["veto_reasons"])


def test_hard_check_freshness_old_rejected():
    old = (datetime.date.today() - datetime.timedelta(days=999)).isoformat()
    h = hard_check(_entry(updated_at=old), CARD, ["vLLM", "RAG"], [], [])
    assert h["passed"] is False
    assert any("时效" in r for r in h["veto_reasons"])


# ---------- 合并仲裁 ----------

def test_merge_no_llm_returns_rule():
    final, flags = merge(70.0, None)
    assert final == 70.0
    assert flags == []


def test_merge_llm_no_evidence_weights_zero():
    final, flags = merge(80.0, _verdict(95.0, evidence=False))
    assert final == 80.0  # 无证据 → LLM 权重归零，退回纯规则
    assert "llm_evidence_missing" in flags


def test_merge_downgrade_capped_conservative():
    # rule=80，LLM 大幅看空（40，差 40>30）且无 red_flags → 保守取 min → final=0.6*80+0.4*40=64
    final, flags = merge(80.0, _verdict(40.0, red_flags=[]))
    assert final == 64.0
    assert "llm_downgrade_capped" in flags


def test_merge_downgrade_trusted_with_red_flags():
    # LLM 看空但带 red_flags → 信任 LLM 低分，不再二次保守
    final, flags = merge(80.0, _verdict(40.0, red_flags=["薪资远低于期望"]))
    assert final == 64.0
    assert "llm_downgrade_capped" not in flags


def test_merge_upgrade_floored_at_gap():
    # rule=50(<gap 60)，LLM 大幅看多（90，差 40>20）→ final=66 封顶在 gap=60，不能抬进 accepted
    final, flags = merge(50.0, _verdict(90.0))
    assert final == 60.0
    assert "llm_upgrade_floored" in flags


# ---------- finalize ----------

def test_finalize_status_accepted():
    h = hard_check(_entry(), CARD, ["vLLM", "RAG"], [], [])
    e = finalize(_entry(), h, _verdict(90.0))
    assert e["final_score"] == 96.0  # 0.6*100 + 0.4*90
    assert e["status"] == "accepted"
    assert e["llm_verdict"]["_flags"] == []


def test_finalize_status_gap_and_excluded():
    h = {"passed": True, "veto_reasons": [], "warnings": [], "rule_score": 65.0,
         "matched_skills": ["vLLM"], "missing_skills": ["PyTorch"]}
    e = finalize(_entry(), dict(h), None)
    assert e["final_score"] == 65.0
    assert e["status"] == "gap"
    assert "gap_tips" in e

    h2 = dict(h, rule_score=40.0)
    e2 = finalize(_entry(), h2, None)
    assert e2["final_score"] == 40.0
    assert e2["status"] == "excluded"


# ---------- 批量门面（LLM 降级 / 注入） ----------

def test_judge_batch_llm_failure_pure_rule(monkeypatch):
    """LLM 抛错 → 该批降级为纯规则（final=rule），行为 ≈ 改造前。"""
    def _boom(*args, **kwargs):
        raise JSAgentError("mock 网络错误")

    monkeypatch.setattr("app.core.llm.llm.chat_json", _boom)
    entries = [_entry(), _entry(title="第二岗位", jd_text="仅 RAG 开发")]
    judged = judge_batch(entries, CARD, ["vLLM", "RAG"], [], [])
    for e in judged:
        assert e["status"] != "excluded"
        assert e["final_score"] == e["match_score"]  # 纯规则降级


def test_judge_batch_with_verdicts(monkeypatch):
    """LLM 正常返回 verdicts → final = 0.6*rule + 0.4*llm，且按 source_url 映射回条目。"""
    calls: dict[str, Any] = {}

    def _fake(system, user, provider_id=None, model=None, max_tokens=None):
        calls["system"] = system
        return {
            "verdicts": [
                {"index": 0, "dimensions": {"jd_fit": {"score": 90, "evidence": "vLLM 部署"},
                                            "job_quality": {"score": 60, "evidence": "JD 完整"},
                                            "growth": {"score": 60, "evidence": "方向契合"}},
                 "overall": {"reason": "契合"}, "red_flags": [], "resume_tips": []},
            ]
        }, {}

    monkeypatch.setattr("app.core.llm.llm.chat_json", _fake)
    entries = judge_batch([_entry()], CARD, ["vLLM", "RAG"], [], [])
    # llm_score = 0.4*90 + 0.3*60 + 0.3*60 = 72 → final = 0.6*100 + 0.4*72 = 88.8
    assert entries[0]["final_score"] == 88.8
    assert entries[0]["status"] == "accepted"
    assert "JUDGE_SYSTEM" not in calls or "软性契合评审员" in calls["system"]


def test_judge_batch_excluded_kept_no_final(monkeypatch):
    """硬约束不过的条目：status=excluded + exclude_reason，不参与 LLM 判定。"""
    def _never(*args, **kwargs):
        raise AssertionError("硬约束不过不应调用 LLM")

    monkeypatch.setattr("app.core.llm.llm.chat_json", _never)
    entries = judge_batch([_entry(city="北京")], CARD, ["vLLM", "RAG"], [], [])
    assert entries[0]["status"] == "excluded"
    assert "final_score" not in entries[0]
