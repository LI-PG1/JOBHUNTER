"""SearchBackendChain 调用逻辑的 mock 本地测试（无真实网络请求）。

运行：python test_search_backends.py
场景覆盖：正常命中 / 失败回退 / 空结果回退 / 冷却跳过与恢复 /
         渠道偏好重排 / 显式指定后端 / 全部失败 / 单例复用。
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from search_backends import SearchBackend, SearchBackendChain, SearchResult  # noqa: E402


# ---------- Mock 后端 ----------

class MockBackend(SearchBackend):
    """可编程 mock 后端：配置结果 / 抛异常 / 空结果，记录调用次数。"""

    def __init__(self, name: str, results: list[SearchResult] | None = None,
                 error: Exception | None = None, empty: bool = False) -> None:
        super().__init__(available=True)
        self.name = name
        self._results = results or []
        self._error = error
        self._empty = empty
        self.calls = 0

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        if self._empty:
            return []
        return self._results[:num]


def _mk_result(title: str, url: str) -> SearchResult:
    return SearchResult(title=title, url=url, snippet=f"{title} 摘要")


def _chain(*backends: MockBackend, cooldown_seconds: int = 120) -> SearchBackendChain:
    return SearchBackendChain(backends=list(backends), cooldown_seconds=cooldown_seconds)


# ---------- 测试 ----------

class TestSearchBackendChain(unittest.TestCase):

    def test_01_first_success(self):
        """第一个可用后端直接命中。"""
        b1 = MockBackend("百度", results=[_mk_result("岗位A", "https://a.com")])
        b2 = MockBackend("360搜索", results=[_mk_result("岗位B", "https://b.com")])
        resp = _chain(b1, b2).search("深圳 AI 开发 招聘")
        self.assertEqual(resp.backend, "百度")
        self.assertEqual(len(resp.results), 1)
        self.assertEqual(resp.results[0].title, "岗位A")
        self.assertEqual(b2.calls, 0)  # 未触发回退

    def test_02_error_fallback(self):
        """后端1 抛异常 → 回退到后端2。"""
        b1 = MockBackend("百度", error=RuntimeError("安全验证页"))
        b2 = MockBackend("360搜索", results=[_mk_result("岗位B", "https://b.com")])
        resp = _chain(b1, b2).search("深圳 AI 开发 招聘")
        self.assertEqual(resp.backend, "360搜索")
        self.assertEqual(len(resp.results), 1)

    def test_03_empty_is_fallback(self):
        """空结果视为失败，继续回退。"""
        b1 = MockBackend("百度", empty=True)
        b2 = MockBackend("Bing", results=[_mk_result("岗位C", "https://c.com")])
        resp = _chain(b1, b2).search("某公司 官网")
        self.assertEqual(resp.backend, "Bing")

    def test_04_all_failed(self):
        """全部失败返回 error 与空结果。"""
        b1 = MockBackend("百度", error=RuntimeError("安全验证页"))
        b2 = MockBackend("360搜索", error=RuntimeError("访问异常"))
        resp = _chain(b1, b2).search("测试")
        self.assertEqual(resp.backend, "全部失败")
        self.assertEqual(resp.results, [])
        self.assertIn("安全验证页", resp.error)   # 聚合两个后端的失败原因
        self.assertIn("访问异常", resp.error)

    def test_05_no_backend(self):
        """无可用后端。"""
        resp = SearchBackendChain(backends=[]).search("测试")
        self.assertEqual(resp.backend, "无可用后端")

    def test_06_cooldown_skip(self):
        """失败后端进入冷却，后续调用被跳过。"""
        b1 = MockBackend("百度", error=RuntimeError("安全验证页"))
        b2 = MockBackend("360搜索", results=[_mk_result("岗位B", "https://b.com")])
        c = _chain(b1, b2)
        c.search("第一次")
        first_calls = b1.calls
        # 冷却期内再次调用：百度被跳过，360 再成功
        resp = c.search("第二次")
        self.assertEqual(resp.backend, "360搜索")
        self.assertEqual(b1.calls, first_calls)  # 冷却期内未再被调用

    def test_07_cooldown_expired(self):
        """冷却过期后恢复尝试。"""
        b1 = MockBackend("百度", error=RuntimeError("安全验证页"))
        b2 = MockBackend("360搜索", results=[_mk_result("岗位B", "https://b.com")])
        c = _chain(b1, b2, cooldown_seconds=0)  # 立即过期
        c.search("第一次")
        first_calls = b1.calls
        c.search("第二次")
        self.assertGreater(b1.calls, first_calls)  # 冷却过期后重新尝试

    def test_08_channel_preference(self):
        """渠道偏好：官网 → Bing → DuckDuckGo → 百度。"""
        bd = MockBackend("百度", results=[_mk_result("官网结果", "https://corp.com")])
        bing = MockBackend("Bing", results=[_mk_result("官网结果2", "https://corp2.com")])
        ddg = MockBackend("DuckDuckGo", results=[_mk_result("官网结果3", "https://corp3.com")])
        c = _chain(bd, bing, ddg)
        resp = c.search("某公司 官网", channel="官网")
        self.assertEqual(resp.backend, "Bing")  # 官网渠道首选 Bing
        self.assertEqual(bd.calls, 0)           # 百度未被触碰

    def test_09_channel_fallback_order(self):
        """渠道首选失败 → 按渠道偏好顺序回退，而非默认链顺序。"""
        bing = MockBackend("Bing", error=RuntimeError("反爬"))
        ddg = MockBackend("DuckDuckGo", results=[_mk_result("官网结果", "https://corp.com")])
        bd = MockBackend("百度", results=[_mk_result("百度结果", "https://bd.com")])
        c = _chain(bd, bing, ddg)
        resp = c.search("某公司 官网", channel="官网")
        self.assertEqual(resp.backend, "DuckDuckGo")  # 官网渠道：Bing 失败 → DDG 而非默认链的百度

    def test_10_preferred_backend(self):
        """显式指定后端优先。"""
        bd = MockBackend("百度", results=[_mk_result("百度结果", "https://bd.com")])
        qh = MockBackend("360搜索", results=[_mk_result("360结果", "https://qh.com")])
        c = _chain(bd, qh)
        resp = c.search("深圳 AI 招聘", preferred="360搜索")
        self.assertEqual(resp.backend, "360搜索")

    def test_11_singleton_isolated(self):
        """两个 chain 实例互不共享冷却状态。"""
        b1 = MockBackend("百度", error=RuntimeError("x"))
        b2 = MockBackend("360搜索", results=[_mk_result("B", "https://b.com")])
        c1 = _chain(b1, b2)
        c2 = _chain(MockBackend("百度", results=[_mk_result("A", "https://a.com")]),
                    MockBackend("360搜索", results=[_mk_result("B", "https://b.com")]))
        c1.search("第一次")
        resp = c2.search("第二次")
        self.assertEqual(resp.backend, "百度")  # c2 的百度未受 c1 冷却影响


if __name__ == "__main__":
    unittest.main(verbosity=2)
