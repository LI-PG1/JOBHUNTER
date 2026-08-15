"""API 联网搜索（契约 §4.2 / search/api_search.py）：Tavily / Serper。

- 限频：固定间隔 interval_seconds（默认 1.1s），进程内单锁保证。
- 降级：Key 缺失或请求失败 → E_SEARCH 50003（调用方捕获后可降级为纯 LLM，不阻塞）。
"""
import asyncio
import os
import time
from typing import List

import httpx

from ..config import Config
from ..core.errors import AppError, E_SEARCH

_TAVILY_URL = "https://api.tavily.com/search"
_SERPER_URL = "https://google.serper.dev/search"


class ApiSearchClient:
    """Tavily/Serper 搜索客户端（无状态单例，多任务串行共用）。"""

    def __init__(self, cfg: Config):
        self.provider = cfg.search.provider
        self.key_env = cfg.search.api_key_env
        self.interval = cfg.search.interval_seconds
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    @property
    def ready(self) -> bool:
        return bool(os.getenv(self.key_env, ""))

    async def search(self, query: str, max_results: int = 5) -> List[dict]:
        """执行搜索，返回 [{title, url, snippet}]；失败抛 E_SEARCH。"""
        key = os.getenv(self.key_env, "")
        if not key:
            raise AppError(E_SEARCH, f"未配置搜索 API Key（环境变量 {self.key_env}）")

        # 固定限频：两次调用间隔 ≥ interval_seconds
        async with self._lock:
            gap = self._last_call + self.interval - time.monotonic()
            if gap > 0:
                await asyncio.sleep(gap)
            self._last_call = time.monotonic()

        try:
            if self.provider == "serper":
                r = await httpx.post(
                    _SERPER_URL,
                    headers={"X-API-KEY": key},
                    json={"q": query, "num": max_results},
                    timeout=20,
                )
                r.raise_for_status()
                items = r.json().get("organic", [])
                results = [
                    {"title": str(o.get("title", "")), "url": str(o.get("link", "")),
                     "snippet": str(o.get("snippet", ""))}
                    for o in items if o.get("link")
                ]
            else:  # tavily（默认）
                r = await httpx.post(
                    _TAVILY_URL,
                    json={"api_key": key, "query": query, "max_results": max_results},
                    timeout=20,
                )
                r.raise_for_status()
                items = r.json().get("results", [])
                results = [
                    {"title": str(x.get("title", "")), "url": str(x.get("url", "")),
                     "snippet": str(x.get("content", ""))}
                    for x in items if x.get("url")
                ]
            return results[:max_results]
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AppError(E_SEARCH, f"搜索失败: {exc}") from exc
