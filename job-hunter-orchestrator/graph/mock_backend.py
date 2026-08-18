"""大脑侧 mock 搜索后端（M4 · 组件化主线的离线数据源）。

match_agent 组件链通过 `build_match_chain(search_chain=...)` 注入搜索后端：
- real 模式：组件自带 SearchBackendChain（真实联网，回退路径 HTTP 工具）
- mock 模式：大脑注入本后端 —— 以 N1 解析出的 target_jobs（含 JD 原文）为种子，
  生成与用户画像相关的岗位条目（snippet=JD），另附 1 条超时效岗位 + 1 条非岗位条目，
  用于覆盖 judge 的时效（H2）/非岗位（is_job）过滤规则。

行为依赖：scrub 的 is_job 初判要求 title 或 url 含岗位信号词（job/招聘/实习…），
故 url 统一带 /job/ 前缀、title 沿用目标岗位名。
"""
from __future__ import annotations

import datetime
from typing import Any

from match_agent.tools.search_backends import SearchBackend, SearchResult


class GoalMockSearchBackend(SearchBackend):
    """以目标岗位清单为种子的确定性 mock 搜索后端（与用户画像联动）。"""

    name = "goal_mock"

    def __init__(self, target_jobs: list[dict[str, Any]] | None = None) -> None:
        self.target_jobs = list(target_jobs or [])

    def search(self, query: str, num: int = 8, channel: str | None = None,
               preferred: str | None = None) -> list[SearchResult]:
        today = datetime.date.today().isoformat()
        old = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
        results = [
            SearchResult(
                title=str((j.get("title") or "岗位")[:64]),
                url=f"https://example.com/job/{i}",
                snippet=str((j.get("jd") or "")[:120]),
                date=today,
            )
            for i, j in enumerate(self.target_jobs)
        ]
        # 噪声样例（judge 过滤规则覆盖）：超时效岗位 + 非岗位条目
        results.append(SearchResult(
            title="已过期岗位", url="https://example.com/job/old",
            snippet="历史岗位信息", date=old))
        results.append(SearchResult(
            title="技术博客文章", url="https://example.com/blog/1",
            snippet="关于深度学习的随笔", date=today))
        return results
