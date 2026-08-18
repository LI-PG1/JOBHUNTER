"""搜索回路状态机单元测试（改造设计 §3）：决策行动 / 回退兜底 / 预算刹车 / 评估器剔除。

mock 搜索插件与 LLM（app.core.llm.llm.chat_json / app.plugins.search.search_plugin.search），不依赖网络。
"""
from __future__ import annotations

from typing import Any

from app.agent.search_loop import run as search_run
from app.core.errors import AgentAbortedError, JSAgentError

CARD = {
    "skills": [{"name": "vLLM", "line": "inference", "confirmed": True}],
    "education": "硕士", "grad_year": "2027", "city": "深圳", "experience_years": None,
    "raw_summary": "大模型应用开发",
}

PLAN = [
    {"q": "AI 应用工程师", "sources": ["招聘平台"], "reason": "主渠道"},
    {"q": "RAG 开发工程师", "sources": ["官网"], "reason": "官网"},
    {"q": "vLLM 部署工程师", "sources": ["社区"], "reason": "社区"},
]


class FakeLLM:
    """可控 LLM：按提示词分发决策器/评估器输出。"""

    def __init__(self, decider: dict | None = None, evaluator: dict | None = None,
                 fail: bool = False) -> None:
        self.decider = decider or {"action": "converge", "queries": [], "note": ""}
        self.evaluator = evaluator or {"novelty": "high", "quality": "good", "discard_urls": [], "note": ""}
        self.fail = fail
        self.systems: list[str] = []

    def chat_json(self, system: str, user: str, provider_id=None, model=None, max_tokens=None):
        self.systems.append(system)
        if self.fail:
            raise JSAgentError("mock LLM 错误")
        if "搜索决策器" in system:
            return dict(self.decider), {}
        if "结果评估器" in system:
            return dict(self.evaluator), {}
        return {}, {}


def _fake_search(query: str, num: int = 8, prefer: str | None = None):
    """每 query 生成唯一结果；记录 prefer 偏好。"""
    _fake_search.calls.append({"query": query, "prefer": prefer})
    assert prefer in (None, "招聘平台", "官网", "社区"), f"非法渠道偏好: {prefer}"
    return {
        "results": [{
            "title": f"岗位-{query}",
            "url": f"https://example.com/jobs/{abs(hash(query))}",
            "snippet": "使用 vLLM 部署服务，负责 RAG 问答系统开发",
            "date": "",
        }],
        "backend": "智谱 web_search",
        "error": "",
    }


def _structure(items, provider_id=None, model=None):
    return [{
        "title": i.get("title", ""), "company": "示例科技", "city": "深圳",
        "salary": "", "jd_text": i.get("snippet", ""), "updated_at": i.get("date", ""),
        "is_job": True, "skill_line": "both", "industry": "互联网", "degree": "本科", "experience": "不限",
    } for i in items]


def _setup(monkeypatch, llm: FakeLLM, max_llm_calls: int = 12):
    _fake_search.calls = []
    monkeypatch.setattr("app.core.llm.llm.chat_json", llm.chat_json)
    monkeypatch.setattr("app.plugins.search.search_plugin.search", _fake_search)
    from app.config import config
    monkeypatch.setitem(config.constraints["search_agent"], "max_llm_calls", max_llm_calls)
    return config


def test_fallback_executes_plan_in_order(monkeypatch):
    """决策器停用（enabled=False）→ 按规划 query 顺序执行，决策器零调用。"""
    llm = FakeLLM()
    _setup(monkeypatch, llm)
    res = search_run(CARD, PLAN, _structure, {
        "enabled": False, "max_results": 20, "min_rounds": 3, "max_rounds": 10,
    })
    # 决策器从未被调用（只有评估器）
    assert not any("搜索决策器" in s for s in llm.systems)
    # 3 条规划 query 全部执行过（history.queries 为已执行 query 字符串）
    executed_qs = [q for h in res["history"] for q in (h.get("queries") or [])]
    for q in PLAN:
        assert q["q"] in executed_qs, f"规划 query 未执行: {q['q']}"
    assert res["entries"], "应有搜索结果收录"
    assert res["converge_reason"]


def test_decider_actions_drive_execution(monkeypatch):
    """决策器给出 expand 行动与 query → 该 query 被执行并收录。"""
    llm = FakeLLM(decider={"action": "expand", "queries": [{"q": "扩散岗位-A", "channel": "官网"}],
                           "note": "扩展同类"})
    _setup(monkeypatch, llm)
    res = search_run(CARD, PLAN, _structure, {
        "enabled": True, "max_results": 20, "min_rounds": 2, "max_rounds": 5,
    })
    titles = [e.get("title", "") for e in res["entries"]]
    assert any("扩散岗位-A" in t for t in titles), "决策器 query 应被实际搜索"
    assert any("搜索决策器" in s for s in llm.systems)
    # 决策 query 自动注入城市前缀
    assert any("深圳" in c.get("query") for c in _fake_search.calls)


def test_decider_converge_stops_after_min_rounds(monkeypatch):
    """决策器首轮即 converge → 至少跑满最低轮数后才停（不突破闸门）。"""
    llm = FakeLLM(decider={"action": "converge", "queries": [], "note": "已达标"})
    _setup(monkeypatch, llm)
    res = search_run(CARD, PLAN, _structure, {
        "enabled": True, "max_results": 20, "min_rounds": 3, "max_rounds": 10,
    })
    assert res["rounds"] >= 3
    assert "decider_converge" in res["converge_reason"]


def test_llm_budget_exhausted_forces_converge(monkeypatch):
    """LLM 调用预算用尽（max_llm_calls=1）→ 强制收敛，不再调用决策器。"""
    llm = FakeLLM(decider={"action": "expand", "queries": [{"q": "A-1"}], "note": ""})
    _setup(monkeypatch, llm, max_llm_calls=1)
    res = search_run(CARD, PLAN, _structure, {
        "enabled": True, "max_results": 20, "min_rounds": 3, "max_rounds": 10,
    })
    assert res["llm_calls"] <= 1, "预算用尽后不应再调用 LLM"
    assert "decider_converge" in res["converge_reason"] or "rounds=" in res["converge_reason"]


def test_evaluator_discard_urls_removed(monkeypatch):
    """评估器返回 discard_urls → 对应收录被剔除。"""
    llm = FakeLLM(
        decider={"action": "rewrite_query", "queries": [{"q": "待剔除岗位", "channel": "招聘平台"}], "note": ""},
        evaluator={"novelty": "medium", "quality": "mixed",
                   "discard_urls": [f"https://example.com/jobs/{abs(hash('深圳 待剔除岗位'))}"], "note": "噪声"},
    )
    _setup(monkeypatch, llm)
    res = search_run(CARD, PLAN, _structure, {
        "enabled": True, "max_results": 20, "min_rounds": 2, "max_rounds": 4,
    })
    urls = [e.get("source_url", "") for e in res["entries"]]
    assert all("待剔除岗位" not in u for u in urls), "discard_urls 应被剔除"


def test_channel_prefer_passed_to_search(monkeypatch):
    """决策器指定 channel → search() 收到对应 prefer 偏好。"""
    llm = FakeLLM(decider={"action": "switch_channel",
                           "queries": [{"q": "官网招聘", "channel": "官网"}], "note": "换渠道"})
    _setup(monkeypatch, llm)
    search_run(CARD, PLAN, _structure, {
        "enabled": True, "max_results": 20, "min_rounds": 1, "max_rounds": 3,
    })
    prefers = [c.get("prefer") for c in _fake_search.calls]
    assert "官网" in prefers, "channel 应映射为 search prefer 偏好"


def test_abort_raises(monkeypatch):
    """用户取消 → 抛 AgentAbortedError。"""
    llm = FakeLLM()
    _setup(monkeypatch, llm)
    called = {"n": 0}

    def _abort() -> bool:
        called["n"] += 1
        return called["n"] >= 1

    try:
        search_run(CARD, PLAN, _structure, {
            "enabled": True, "max_results": 20, "min_rounds": 3, "max_rounds": 10,
            "is_aborted": _abort,
        })
        raise AssertionError("应抛 AgentAbortedError")
    except AgentAbortedError:
        pass


def test_fallback_on_decider_failure(monkeypatch):
    """决策器 LLM 失败 → 降级按规划 query 顺序执行（不中断）。"""
    llm = FakeLLM(fail=True)
    _setup(monkeypatch, llm)
    res = search_run(CARD, PLAN, _structure, {
        "enabled": True, "max_results": 20, "min_rounds": 3, "max_rounds": 10,
    })
    executed_qs = [q for h in res["history"] for q in (h.get("queries") or [])]
    assert all(q["q"] in executed_qs for q in PLAN), "LLM 失败也应执行全部规划 query"
    assert res["entries"]
