"""match_agent 搜索后端 fetch 工具类（独立于 JS-Agent 工程）。

将《JS搜索回路详细设计.md §4.2》的七种搜索后端封装为统一接口的 fetch 工具类：
  智谱 web_search / Tavily / 百度 / 360 / DuckDuckGo / Bing / Playwright

设计要点：
- 独立：Key 通过构造函数注入，不依赖任何工程的 config/key_store；
  网络请求使用标准库 urllib（百度/360 优先 curl_cffi Chrome TLS 指纹，未装自动降级）
- 统一接口：`SearchBackend.search(query, num) -> list[SearchResult]`
- 组合器 `SearchBackendChain`：可用性探测 + 优先级回退 + 失败冷却 + 渠道偏好映射
- 对应文档：§4.2 后端 API 明细 / §3.2 渠道→后端偏好映射 / §5.2 执行层错误处理
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


# ---------- 数据结构 ----------

@dataclass
class SearchResult:
    """统一搜索结果条目。"""
    title: str
    url: str
    snippet: str = ""
    date: str = ""


@dataclass
class SearchResponse:
    """组合器返回值：结果 + 实际命中的后端 + 错误（全失败时）。"""
    results: list[SearchResult]
    backend: str
    error: str = ""


# ---------- HTTP 基础 ----------

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _http_json(url: str, payload: dict[str, Any] | None, headers: dict[str, str] | None,
               timeout: int = 30) -> dict[str, Any]:
    """POST/GET JSON 请求（搜索 API 用）。"""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers=headers or {"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_html(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    """带 Chrome TLS 指纹的 HTML GET：curl_cffi 优先（绕过百度等反爬），未安装时降级 urllib。"""
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore
        resp = cffi_requests.get(url, impersonate="chrome", timeout=timeout,
                                 headers=headers or {"User-Agent": _DEFAULT_UA})
        return resp.text
    except ImportError:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": _DEFAULT_UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")


# ---------- 后端基类 ----------

class SearchBackend(ABC):
    """单个搜索后端基类。子类必须定义 name 并实现 search。"""

    name = "base"

    def __init__(self, available: bool = True) -> None:
        self.available = available

    @abstractmethod
    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        """执行搜索。失败/被反爬应抛异常，由组合器统一回退与冷却。"""


# ---------- 1. 智谱 web_search_pro（有 GLM Key 时可用） ----------

class ZhipuSearchBackend(SearchBackend):
    """智谱 web_search_pro：GLM Key 即可用，模型内置搜索工具。"""

    name = "智谱 web_search"
    _URL = "https://open.bigmodel.cn/api/paas/v4/tools/web_search_pro"
    _TIMEOUT = 45

    def __init__(self, api_key: str) -> None:
        super().__init__(available=bool(api_key))
        self._key = api_key

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        body = {
            "search_engine": "search_std",
            "search_query": query,
            "max_result": min(num, 10),
            "tools": [{"type": "web_search", "web_search": {"enable": True, "search_query": query}}],
        }
        data = _http_json(self._URL, body,
                          {"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"},
                          timeout=self._TIMEOUT)
        out: list[SearchResult] = []
        try:
            for choice in data.get("choices", []):
                for tc in choice.get("message", {}).get("tool_calls", []):
                    for item in tc.get("search_result", []):
                        out.append(SearchResult(
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("content", ""),
                            date=item.get("date", ""),
                        ))
        except (KeyError, TypeError, AttributeError):
            return []
        return out[:num]


# ---------- 2. Tavily Search API（有 Key 时可用） ----------

class TavilySearchBackend(SearchBackend):
    """Tavily Search API。"""

    name = "Tavily"
    _URL = "https://api.tavily.com/search"
    _TIMEOUT = 45

    def __init__(self, api_key: str) -> None:
        super().__init__(available=bool(api_key))
        self._key = api_key

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        data = _http_json(
            self._URL,
            {"api_key": self._key, "query": query, "max_results": min(num, 10),
             "search_depth": "advanced", "include_domains": [], "include_raw_content": False},
            {"Content-Type": "application/json"},
            timeout=self._TIMEOUT,
        )
        return [
            SearchResult(
                title=r.get("title", ""), url=r.get("url", ""),
                snippet=r.get("content", ""), date=r.get("published_date", ""),
            )
            for r in data.get("results", [])[:num]
        ]


# ---------- 3. 百度（免 Key，大陆可达，招聘页命中率高） ----------

class BaiduSearchBackend(SearchBackend):
    """百度网页搜索：免 Key。curl_cffi 指纹反爬，偶发安全验证页抛异常由组合器冷却回退。

    解析：按 `result c-container` 结果块切分，标题取 h3>a；真实链接优先取 `mu` 属性
    （百度 link 重定向前的真实站址，如 zhipin.com）；摘要取结果块内 `s-data` 的 summaryData。
    """

    name = "百度"

    def __init__(self, available: bool = True) -> None:
        super().__init__(available=available)

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        url = "https://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query, "ie": "utf-8"})
        html = _http_get_html(url)
        if len(html) < 20000 or "安全验证" in html[:2000]:
            raise RuntimeError("百度返回安全验证页")
        out: list[SearchResult] = []
        for blk in re.split(r'(?=<div class="result c-container)', html)[1:]:
            m = re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
            if not m:
                continue
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title:
                continue
            href = m.group(1)
            mu = re.search(r'mu="([^"]+)"', blk)
            if mu:
                href = mu.group(1)
            snippet = ""
            sd = re.search(r'"summaryData":\{"generalLines":\[.*?"text":"(.*?)"', blk, re.S)
            if sd:
                snippet = re.sub(r"<[^>]+>", "", sd.group(1)).replace('\\"', '"').strip()[:300]
            out.append(SearchResult(title=title, url=href, snippet=snippet))
            if len(out) >= num:
                break
        return out


# ---------- 4. 360 搜索（免 Key，移动端优先，桌面端兜底） ----------

class QihooSearchBackend(SearchBackend):
    """360 搜索：免 Key、大陆可达，招聘页命中率高（移动端 m.so.com 优先，桌面端兜底）。"""

    name = "360搜索"

    def __init__(self, available: bool = True) -> None:
        super().__init__(available=available)

    @staticmethod
    def _real_url(href: str) -> str:
        """m.so.com/jump?u=<urlencoded> 重定向 → 真实链接。"""
        if "m.so.com/jump" in href:
            href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [href])[0]
            href = urllib.parse.unquote(href)
        return href

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        # 移动端优先：<a class=alink href="jump?u=..."><h3 class="res-title">…</h3><p class="g-main summary">…</p></a>
        url = "https://m.so.com/s?" + urllib.parse.urlencode({"q": query})
        html = _http_get_html(url)
        if len(html) < 10000 or "访问异常" in html[:2000]:
            # 移动端被拦 → 桌面端（<h3><a> 结构）兜底
            url = "https://www.so.com/s?" + urllib.parse.urlencode({"q": query})
            html = _http_get_html(url)
            if len(html) < 10000 or "访问异常" in html[:2000]:
                raise RuntimeError("360 返回访问异常页")
            out: list[SearchResult] = []
            for m in re.finditer(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if not title:
                    continue
                out.append(SearchResult(title=title, url=m.group(1)))
                if len(out) >= num:
                    break
            return out
        out = []
        for m in re.finditer(
            r'<a class=alink href="([^"]+)"[^>]*>\s*<h3 class="res-title">(.*?)</h3>\s*<p class="g-main summary">(.*?)</p>',
            html, re.S,
        ):
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title:
                continue
            out.append(SearchResult(
                title=title, url=self._real_url(m.group(1)),
                snippet=re.sub(r"<[^>]+>", "", m.group(3)).strip(),
            ))
            if len(out) >= num:
                break
        return out


# ---------- 5. DuckDuckGo html 端点（免 Key，非官方，灰区） ----------

class DDGSSearchBackend(SearchBackend):
    """DuckDuckGo html 端点：免 Key、非官方；灰区有限授权，结果需复核；国内不可达时自动失败。"""

    name = "DuckDuckGo"
    _TIMEOUT = 8

    def __init__(self, available: bool = True) -> None:
        super().__init__(available=available)

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_UA})
        with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        out: list[SearchResult] = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            href = urllib.parse.unquote(href)
            # 过滤 DDG 重定向
            if "uddg=" in href:
                href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
            if not title:
                continue
            out.append(SearchResult(title=title, url=href))
            if len(out) >= num:
                break
        return out


# ---------- 6. Bing（免 Key，官网类查询兜底） ----------

class BingSearchBackend(SearchBackend):
    """必应（cn.bing.com）HTML 端点：免 Key、大陆可达；有反爬降级风险，仅作官网类查询兜底。"""

    name = "Bing"
    _TIMEOUT = 30

    def __init__(self, available: bool = True) -> None:
        super().__init__(available=available)

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        url = "https://cn.bing.com/search?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
        with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        out: list[SearchResult] = []
        for it in re.findall(r'<li class="b_algo".*?</li>', html, re.S):
            m = re.search(r'<h2[^>]*>\s*<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>', it, re.S)
            if not m:
                m = re.search(r'<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>', it, re.S)
            if not m:
                continue
            href = m.group(1)
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title:
                continue
            sm = re.search(r'<p[^>]*>(.*?)</p>', it, re.S)
            snippet = re.sub(r"<[^>]+>", "", sm.group(1)).strip() if sm else ""
            out.append(SearchResult(title=title, url=href, snippet=snippet))
            if len(out) >= num:
                break
        return out


# ---------- 7. Playwright 真实浏览器（需安装 ~150MB，稳定性最高） ----------

class PlaywrightSearchBackend(SearchBackend):
    """Playwright 无头浏览器：真实 Chrome 访问 百度→360→Bing（免反爬）。需用户确认安装：

        pip install playwright && playwright install chromium
    """

    name = "Playwright"

    def __init__(self, available: bool = False) -> None:
        super().__init__(available=available)

    def _search_browser(self, browser: Any, query: str, num: int) -> list[SearchResult]:
        engines = [
            ("https://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query, "ie": "utf-8"}), "h3 a"),
            ("https://www.so.com/s?" + urllib.parse.urlencode({"q": query}), "h3 a"),
            ("https://cn.bing.com/search?" + urllib.parse.urlencode({"q": query}), "li.b_algo h2 a"),
        ]
        for url, sel in engines:
            try:
                page = browser.new_page()
                page.goto(url, timeout=20000)
                page.wait_for_timeout(1200)
                # 反爬页快速跳过（百度安全验证/360 访问异常），不等待超时
                t = page.title() or ""
                if any(k in t for k in ("安全验证", "访问异常", "验证码", "异常访问")):
                    page.close()
                    continue
                page.wait_for_selector(sel, timeout=8000)
                out: list[SearchResult] = []
                for a in page.query_selector_all(sel)[:num]:
                    href = a.get_attribute("href") or ""
                    title = a.inner_text().strip()
                    if title and href.startswith("http"):
                        out.append(SearchResult(title=title, url=href))
                page.close()
                if out:
                    return out
            except Exception:  # noqa: BLE001  # 单引擎失败不致命，继续下一引擎
                continue
        return []

    def search(self, query: str, num: int = 8) -> list[SearchResult]:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                return self._search_browser(browser, query, num)
            finally:
                browser.close()


# ---------- 组合器 ----------

# 渠道 → 后端偏好映射（《JS搜索回路详细设计.md §3.2》）
CHANNEL_BACKENDS: dict[str, list[str]] = {
    "招聘平台": ["百度", "360搜索", "Playwright"],
    "官网": ["Bing", "DuckDuckGo", "百度"],
    "社区": ["百度", "360搜索", "Bing"],
}


def playwright_available() -> bool:
    """探测 Playwright 浏览器是否已安装（chromium 可执行文件存在）。"""
    try:
        import playwright  # noqa: F401
        ms = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
        return bool(
            glob_match(os.path.join(ms, "chromium-*", "chrome-win64", "chrome.exe"))
            or glob_match(os.path.join(ms, "chromium-*", "chrome.exe"))
        )
    except ImportError:
        return False


def glob_match(pattern: str) -> bool:
    import glob
    return bool(glob.glob(pattern))


class SearchBackendChain:
    """搜索后端组合器：优先级回退 + 失败冷却 + 渠道偏好映射。

    用法：
        chain = SearchBackendChain(zhipu_key="", tavily_key="")
        resp = chain.search("深圳 AI应用开发工程师 招聘", num=8)          # 默认链
        resp = chain.search("某公司 官网", num=8, channel="官网")          # 渠道偏好链
        resp = chain.search("xxx", num=8, preferred="百度")                # 指定后端优先
    """

    COOLDOWN_SECONDS = 120  # 后端异常后冷却，避免限流窗口内反复超时

    def __init__(self, zhipu_key: str = "", tavily_key: str = "",
                 backends: list[SearchBackend] | None = None,
                 cooldown_seconds: int = 120) -> None:
        self._cooldown: dict[str, float] = {}
        self.cooldown_seconds = cooldown_seconds
        self.backends = backends if backends is not None else self._default_backends(zhipu_key, tavily_key)

    def _default_backends(self, zhipu_key: str, tavily_key: str) -> list[SearchBackend]:
        """默认链：智谱 → Tavily → 百度 → Playwright → 360 → DDGS → Bing（与文档 §4.2 一致）。"""
        chain: list[SearchBackend] = []
        if zhipu_key:
            chain.append(ZhipuSearchBackend(zhipu_key))
        if tavily_key:
            chain.append(TavilySearchBackend(tavily_key))
        chain.append(BaiduSearchBackend())
        if playwright_available():
            chain.append(PlaywrightSearchBackend(available=True))
        chain.append(QihooSearchBackend())
        chain.append(DDGSSearchBackend())
        chain.append(BingSearchBackend())
        return chain

    def refresh(self, zhipu_key: str = "", tavily_key: str = "") -> None:
        """配置变更后重建后端链（清空冷却）。"""
        self._cooldown.clear()
        self.backends = self._default_backends(zhipu_key, tavily_key)

    def active_chain(self) -> list[str]:
        return [b.name for b in self.backends if b.available]

    def _in_cooldown(self, name: str) -> bool:
        return time.time() < self._cooldown.get(name, 0)

    def _ordered(self, channel: str | None, preferred: str | None) -> list[SearchBackend]:
        """按渠道偏好/显式指定重排后端（未命中偏好保持默认优先级）。"""
        order = [b for b in self.backends if b.available]
        if preferred:
            return sorted(order, key=lambda b: b.name != preferred)
        if channel and channel in CHANNEL_BACKENDS:
            prefs = CHANNEL_BACKENDS[channel]
            order.sort(key=lambda b: prefs.index(b.name) if b.name in prefs else len(prefs))
            return order
        return order

    def search(self, query: str, num: int = 8,
               channel: str | None = None,
               preferred: str | None = None) -> SearchResponse:
        """按优先级执行，失败自动回退下一后端；异常后端进入冷却。全失败时聚合各后端错误。"""
        errors: list[str] = []
        for backend in self._ordered(channel, preferred):
            if self._in_cooldown(backend.name):
                continue
            try:
                results = backend.search(query, num)
                if results:
                    return SearchResponse(results=results, backend=backend.name)
                errors.append(f"{backend.name}: 返回空结果")
            except Exception as exc:  # noqa: BLE001
                self._cooldown[backend.name] = time.time() + self.cooldown_seconds
                errors.append(f"{backend.name}: {exc}")
                time.sleep(0.5)  # 反爬触发后短暂间隔，避免快速连续请求
        if errors:
            return SearchResponse(results=[], backend="全部失败", error="；".join(errors))
        return SearchResponse(results=[], backend="无可用后端", error="未配置任何可用后端")


# 模块级单例（组件内复用；多实例互不共享冷却状态）
default_chain = SearchBackendChain()
