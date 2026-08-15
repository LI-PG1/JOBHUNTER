"""结果存储：匹配清单 md 落盘到 output/。"""
from __future__ import annotations

import datetime
from pathlib import Path

from .config import config


def save_markdown(content: str, prefix: str = "match") -> Path:
    config.storage_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = config.storage_dir / f"{prefix}_{ts}.md"
    path.write_text(content, encoding="utf-8")
    return path
