"""match_agent 搜索后端 fake 实现（mock 模式 / 测试用）。

离线可跑通 P0 线性链：query 含岗位/技能词 → 返回匹配岗位组；
另追加 1 个超时效岗位 + 1 个非岗位条目，用于验证 judge 过滤规则。
"""
from __future__ import annotations

from match_agent.tools.search_backends import SearchBackend, SearchResponse, SearchResult

_GROUPS: dict[str, list[tuple[str, str, str, str]]] = {
    # 关键词 → (title, company, snippet, date)
    "high": [
        ("AI应用开发工程师", "示例科技", "Python 深度学习 大模型 推理优化", "2026-08-01"),
        ("深度学习算法实习生", "示例智造", "Python PyTorch 深度学习 图像识别", "2026-08-01"),
    ],
    "low": [
        ("数据分析师", "示例数据", "SQL Excel 报表 BI", "2026-08-01"),
    ],
}

_HIGH_HINT = ("算法", "深度学习", "python", "大模型", "ai", "推理", "实习", "工程师")


class FakeSearchBackend(SearchBackend):
    name = "fake"

    def search(self, query: str, num: int = 8, channel: str | None = None,
               preferred: str | None = None) -> list[SearchResult]:
        q = query.lower()
        group = "high" if any(h in q for h in _HIGH_HINT) else "low"
        results = [
            SearchResult(title=t, url=f"https://fake.jobs/{i}", snippet=s, date=d)
            for i, (t, _, s, d) in enumerate(_GROUPS[group])
        ]
        # 过滤规则验证样例
        results.append(SearchResult(
            title="已过期岗位", url="https://fake.jobs/old",
            snippet="Python 开发", date="2025-01-01",
        ))
        results.append(SearchResult(
            title="技术博客文章", url="https://fake.blog/1",
            snippet="关于深度学习的随笔", date="2026-08-02",
        ))
        return results


def fake_response(query: str) -> SearchResponse:
    """直接构造 SearchResponse（供注入）。"""
    return SearchResponse(results=FakeSearchBackend().search(query), backend="fake")
