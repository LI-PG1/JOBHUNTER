"""N10 本地 tracker 存储（M4 · 无子项目模型下的进程内实现）。

替代外部 interview-tracker 服务：投递/面试记录写入本地 JSON（原子写 + 线程锁）。
契约：
    append(records) -> list   追加记录，返回全量
    load() -> list            全量记录
持久化路径默认 components/tracker_agent/data/records.json，
可用环境变量 TRACKER_DATA_DIR 重定向（服务/桌面版安装目录场景）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


class TrackerStore:
    """线程安全的本地 JSON 记录存储（追加式）。"""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir or os.getenv("TRACKER_DATA_DIR") or DEFAULT_DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "records.json"
        self._lock = threading.Lock()

    def load(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read()

    def append(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """追加记录并返回全量（去重：同 job 同 status 不重复追加）。"""
        with self._lock:
            cur = self._read()
            for r in records:
                key = (str(r.get("job", "")), str(r.get("status", "")))
                if key in {(str(x.get("job", "")), str(x.get("status", ""))) for x in cur}:
                    continue
                cur.append(dict(r))
            self._write(cur)
            return cur

    def _read(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _write(self, records: list[dict[str, Any]]) -> None:
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)
