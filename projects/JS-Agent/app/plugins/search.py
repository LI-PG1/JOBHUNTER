"""通用搜索插件（方案 v0.5 §7）：后端自动探测 + 自动回退，零手动配置。

后端优先级（自动探测可用性）：
1. 智谱 web_search_pro（GLM Key 存在且配置了搜索工具）
2. Tavily（Tavily Key 存在）
3. 百度（免 Key，大陆可达，招聘页命中率高；curl_cffi Chrome TLS 指纹反爬，未装则降级 urllib）
4. Playwright（真实浏览器搜百度/360，稳定性最高；需用户确认下载 ~150MB；百度限流时优先兜底）
5. 360搜索（免 Key；移动端优先，来源多为猎聘/智联/BOSS直聘；反爬拦截时自动回退）
6. ddgs（免 Key，非官方，灰区有限授权；国内不可达时自动跳过）
7. Bing（免 Key；HTML 端点有反爬降级风险，仅作官网类查询兜底）

search(query, num) → [{"title","url","snippet","date"}]
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any

from ..config import config, key_store


def _http_json(url: str, payload: dict[str, Any] | None, headers: dict[str, str] | None, timeout: int = 30) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {"Content-Type": "application/json"}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class SearchBackend:
    """单个搜索后端基类。"""

    name = "base"
    available = False

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:  # pragma: no cover
        raise NotImplementedError


class ZhipuBackend(SearchBackend):
    """智谱 web_search_pro（GLM Key 即可用，模型内置工具）。"""

    name = "智谱 web_search"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self.available = bool(api_key)

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:
        body = {
            "search_engine": "search_std",
            "search_query": query,
            "max_result": min(num, 10),
            "tools": [{"type": "web_search", "web_search": {"enable": True, "search_query": query}}],
        }
        data = _http_json(
            "https://open.bigmodel.cn/api/paas/v4/tools/web_search_pro",
            body,
            {"Content-Type": "application/json", "Authorization": f"Bearer {self._key}"},
            timeout=45,
        )
        results: list[dict[str, str]] = []
        try:
            for choice in data.get("choices", []):
                for tc in choice.get("message", {}).get("tool_calls", []):
                    for item in tc.get("search_result", []):
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "snippet": item.get("content", ""),
                            "date": item.get("date", ""),
                        })
        except (KeyError, TypeError, AttributeError):
            return []
        return results[:num]


class TavilyBackend(SearchBackend):
    """Tavily Search API（有 Key 时可用）。"""

    name = "Tavily"

    def __init__(self, api_key: str) -> None:
        self._key = api_key
        self.available = bool(api_key)

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:
        data = _http_json(
            "https://api.tavily.com/search",
            {"api_key": self._key, "query": query, "max_results": min(num, 10),
             "search_depth": "advanced", "include_domains": [], "include_raw_content": False},
            {"Content-Type": "application/json"},
            timeout=45,
        )
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", ""), "date": r.get("published_date", "")}
            for r in data.get("results", [])[:num]
        ]


class DDGSBackend(SearchBackend):
    """DuckDuckGo html 端点（免 Key，非官方；灰区有限授权，结果需复核）。"""

    name = "DuckDuckGo"

    def __init__(self) -> None:
        self.available = True

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results: list[dict[str, str]] = []
        # 解析 result 块
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            href = urllib.parse.unquote(href)
            # 过滤 DDG 重定向
            if "uddg=" in href:
                href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
            if not title:
                continue
            results.append({"title": title, "url": href, "snippet": "", "date": ""})
            if len(results) >= num:
                break
        return results


_HTML_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _http_get_html(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    """带 Chrome TLS 指纹的 HTML GET：curl_cffi 优先（绕过百度等反爬），未安装时降级 urllib。"""
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome", timeout=timeout, headers=headers or _HTML_UA)
        return resp.text
    except ImportError:
        req = urllib.request.Request(url, headers=headers or _HTML_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")


class BaiduBackend(SearchBackend):
    """百度网页搜索：免 Key、大陆可达，招聘页命中率高（curl_cffi 指纹反爬，偶发安全验证页自动回退）。

    解析：按 `result c-container` 结果块切分，标题取 h3>a，真实链接优先取 `mu` 属性（
    百度 link 重定向前的真实站址，如 zhipin.com），摘要取结果块内 `s-data` 的 summaryData。
    """

    name = "百度"

    def __init__(self) -> None:
        self.available = True

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:
        url = "https://www.baidu.com/s?" + urllib.parse.urlencode({"wd": query, "ie": "utf-8"})
        html = _http_get_html(url)
        if len(html) < 20000 or "安全验证" in html[:2000]:
            raise RuntimeError("百度返回安全验证页")
        results: list[dict[str, str]] = []
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
            results.append({"title": title, "url": href, "snippet": snippet, "date": ""})
            if len(results) >= num:
                break
        return results


class QihooBackend(SearchBackend):
    """360 搜索：免 Key、大陆可达，招聘页命中率高（移动端 m.so.com 优先，桌面端兜底）。"""

    name = "360搜索"

    def __init__(self) -> None:
        self.available = True

    @staticmethod
    def _real_url(href: str) -> str:
        """m.so.com/jump?u=<urlencoded> 重定向 → 真实链接。"""
        if "m.so.com/jump" in href:
            href = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("u", [href])[0]
            href = urllib.parse.unquote(href)
        return href

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:
        # 移动端优先：结构为 <a class=alink href="jump?u=..."><h3 class="res-title">…</h3><p class="g-main summary">…</p></a>
        url = "https://m.so.com/s?" + urllib.parse.urlencode({"q": query})
        html = _http_get_html(url)
        if len(html) < 10000 or "访问异常" in html[:2000]:
            # 移动端被拦 → 桌面端（<h3><a> 结构）兜底
            url = "https://www.so.com/s?" + urllib.parse.urlencode({"q": query})
            html = _http_get_html(url)
            if len(html) < 10000 or "访问异常" in html[:2000]:
                raise RuntimeError("360 返回访问异常页")
            results: list[dict[str, str]] = []
            for m in re.finditer(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if not title:
                    continue
                results.append({"title": title, "url": m.group(1), "snippet": "", "date": ""})
                if len(results) >= num:
                    break
            return results
        results: list[dict[str, str]] = []
        for m in re.finditer(
            r'<a class=alink href="([^"]+)"[^>]*>\s*<h3 class="res-title">(.*?)</h3>\s*<p class="g-main summary">(.*?)</p>',
            html,
            re.S,
        ):
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            if not title:
                continue
            results.append({
                "title": title,
                "url": self._real_url(m.group(1)),
                "snippet": re.sub(r"<[^>]+>", "", m.group(3)).strip(),
                "date": "",
            })
            if len(results) >= num:
                break
        return results


class BingBackend(SearchBackend):
    """必应（cn.bing.com）HTML 端点：免 Key、大陆可达（DuckDuckGo 在国内不可用时的主力回退）。"""

    name = "Bing"

    def __init__(self) -> None:
        self.available = True

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:
        url = "https://cn.bing.com/search?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        results: list[dict[str, str]] = []
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
            results.append({"title": title, "url": href, "snippet": snippet, "date": ""})
            if len(results) >= num:
                break
        return results


class PlaywrightBackend(SearchBackend):
    """Playwright 无头浏览器：真实 Chrome 访问百度（免反爬，稳定性最高），失败依次兜底 360/Bing。

    需用户确认安装：pip install playwright && playwright install chromium（~150MB）。
    """

    name = "Playwright"

    def __init__(self) -> None:
        self.available = False

    def _search_browser(self, browser, query: str, num: int) -> list[dict[str, str]]:
        """用真实浏览器依次尝试 百度 → 360 → Bing，返回解析后的结果。"""
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
                out: list[dict[str, str]] = []
                for a in page.query_selector_all(sel)[:num]:
                    href = a.get_attribute("href") or ""
                    title = a.inner_text().strip()
                    if title and href.startswith("http"):
                        out.append({"title": title, "url": href, "snippet": "", "date": ""})
                page.close()
                if out:
                    return out
            except Exception:  # noqa: BLE001  # 单引擎失败不致命，继续下一引擎
                continue
        return []

    def search(self, query: str, num: int = 8) -> list[dict[str, str]]:  # pragma: no cover
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                return self._search_browser(browser, query, num)
            finally:
                browser.close()


# 渠道 → 后端偏好（搜索回路 §3.3）：决策器选 channel 时优先尝试，失败仍按原链回退
CHANNEL_PREFER: dict[str, list[str]] = {
    "招聘平台": ["智谱 web_search", "百度", "360搜索"],
    "官网": ["百度", "智谱 web_search"],
    "社区": ["智谱 web_search", "DuckDuckGo", "Bing"],
}


class SearchPlugin:
    """搜索插件：自动探测后端 + 运行时自动回退 + 失败冷却（反爬限流窗口跳过）。"""

    COOLDOWN_SECONDS = 120  # 后端异常后冷却，避免限流窗口内反复超时

    def __init__(self) -> None:
        self.backends: list[SearchBackend] = []
        self._cooldown: dict[str, float] = {}
        self.refresh()

    def refresh(self) -> None:
        """启动/配置后调用：重新探测可用后端并按优先级排序。"""
        self._cooldown.clear()
        keys = key_store.load()
        zhipu_key = keys.get("zhipu", {}).get("api_key", "")
        tavily_key = keys.get("tavily", {}).get("api_key", "") or ""
        backends: list[SearchBackend] = []
        if zhipu_key:
            backends.append(ZhipuBackend(zhipu_key))
        if tavily_key:
            backends.append(TavilyBackend(tavily_key))
        backends.append(BaiduBackend())
        # Playwright（真实浏览器）紧跟百度：百度限流/反爬时优先用浏览器兜底，
        # 避免落到 Bing 等「有结果但全是无关页」的后端（其垃圾结果会短路链路）
        try:
            import playwright  # noqa: F401
            import glob
            ms = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
            found = bool(
                glob.glob(os.path.join(ms, "chromium-*", "chrome-win64", "chrome.exe"))
                or glob.glob(os.path.join(ms, "chromium-*", "chrome.exe"))
            )
            if found and config.plugins_state.get("playwright", {}).get("enabled", True):
                pb = PlaywrightBackend()
                pb.available = True
                backends.append(pb)
        except ImportError:
            pass
        backends.append(QihooBackend())
        backends.append(DDGSBackend())
        backends.append(BingBackend())
        self.backends = backends

    def active_chain(self) -> list[str]:
        return [b.name for b in self.backends if b.available]

    def _in_cooldown(self, name: str) -> bool:
        return time.time() < self._cooldown.get(name, 0)

    def search(self, query: str, num: int = 8, prefer: str | None = None) -> dict[str, Any]:
        """按优先级执行，失败自动回退下一后端；异常后端进入冷却。返回 {"results", "backend"}。

        prefer：渠道偏好（招聘平台/官网/社区，映射 CHANNEL_PREFER）——偏好后端先试，
        失败仍按原链回退（回退链本身是确定性代码，LLM 只做行动选择）。
        """
        order = self.backends
        if prefer:
            prefs = [b for b in order if b.name in CHANNEL_PREFER.get(prefer, [])]
            if prefs:
                order = prefs + [b for b in order if b.name not in CHANNEL_PREFER.get(prefer, [])]
        last_err: Exception | None = None
        for backend in order:
            if not backend.available:
                continue
            if self._in_cooldown(backend.name):
                continue
            try:
                results = backend.search(query, num)
                if results:
                    return {"results": results, "backend": backend.name}
                last_err = RuntimeError(f"{backend.name} 返回空结果")
            except Exception as exc:  # noqa: BLE001
                self._cooldown[backend.name] = time.time() + self.COOLDOWN_SECONDS
                last_err = exc
                time.sleep(0.5)
        if last_err:
            return {"results": [], "backend": "全部失败", "error": str(last_err)}
        return {"results": [], "backend": "无可用后端", "error": "请先配置 Key 或执行一键配置"}


search_plugin = SearchPlugin()
