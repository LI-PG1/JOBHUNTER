"""通用抓取插件（方案 v0.5 §4.1）：多级回退，自动选最优通道。

优先级：Jina Reader（免费 1000 万 token，SPA 渲染强）→ Trafilatura（本地）→ urllib 直连 → Playwright（兜底）。
"""
from __future__ import annotations

import re
import urllib.request
from typing import Any


def _http_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JS-Agent"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


class FetchPlugin:
    name = "fetch"

    def fetch(self, url: str) -> dict[str, Any]:
        """抓取网页正文，返回 {"text","backend","error"}。多级回退。"""
        # ① Jina Reader（免费代理渲染）
        try:
            text = _http_text("https://r.jina.ai/" + url, timeout=45)
            if text and len(text.strip()) > 100:
                return {"text": text, "backend": "jina"}
        except Exception:  # noqa: BLE001
            pass

        # ② Trafilatura（本地）
        try:
            import trafilatura  # type: ignore
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded)
                if text and len(text.strip()) > 50:
                    return {"text": text, "backend": "trafilatura"}
        except Exception:  # noqa: BLE001
            pass

        # ③ urllib 直连（HTML 页兜底）
        try:
            html = _http_text(url, timeout=30)
            text = _html_to_text(html)
            if text and len(text.strip()) > 50:
                return {"text": text, "backend": "urllib"}
        except Exception as exc:  # noqa: BLE001
            return {"text": "", "backend": "failed", "error": str(exc)}

        return {"text": "", "backend": "failed", "error": "所有抓取通道失败"}


def _html_to_text(html: str) -> str:
    """极简 HTML→文本（脚本/样式剔除 + 标签剥离）。"""
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "\n", html)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in html.splitlines()]
    return "\n".join(l for l in lines if l)


fetch_plugin = FetchPlugin()
