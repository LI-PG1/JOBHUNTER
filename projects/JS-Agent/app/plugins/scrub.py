"""数据洗涤：去重 / 去噪 / 字段归一化（时效与地域过滤由收录 Gate 负责）。"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

# 常见广告/噪声 URL 特征（百度 link 重定向是搜索结果的真实来源，不作噪声）
NOISE_URL_PATTERNS = [
    r"zhidao\.baidu\.com",
    r"baijiahao\.baidu\.com",
    r"/search\?",
]

# 需人工确认是否抓取的招聘平台主机名（灰区，抓取后人工复核）
GREY_HOSTS = ["zhipin.com", "liepin.com", "lagou.com", "51job.com", "zhaopin.com"]


def clean_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    return url


def is_noise(url: str) -> bool:
    u = clean_url(url).lower()
    return any(re.search(p, u) for p in NOISE_URL_PATTERNS)


def dedupe(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 title+company 去重，保留最新（updated_at 大者优先）。"""
    seen: dict[str, dict[str, Any]] = {}
    for e in entries:
        key = f"{e.get('company','')}|{e.get('title','')}".lower()
        if key in seen:
            prev = seen[key]
            if (e.get("updated_at") or "") >= (prev.get("updated_at") or ""):
                seen[key] = e
        else:
            seen[key] = e
    return list(seen.values())


def normalize(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in entries:
        e = dict(e)
        e["source_url"] = clean_url(e.get("source_url", ""))
        for f in ("title", "company", "city", "salary"):
            e[f] = str(e.get(f, "")).strip()
        if is_noise(e["source_url"]):
            continue
        out.append(e)
    return out
