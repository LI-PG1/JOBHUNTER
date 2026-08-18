"""生成缓存（契约 §5.4）：JD 分析缓存 + 板块级增量缓存。

- key 计算：SHA256(各组成部分规范化拼接) 取前 20 位。
- JD 分析缓存：SHA256(Jobs[] | rules.jobs.version)。
- 板块缓存：SHA256(block | factsheet.version | rules.version | resumeInputHash)。
- 失效：rules/prompt 版本变更 → 全量失效（key 变化即失效）；用户编辑 → 输入哈希变化自动失效。
"""
import hashlib
import json
from pathlib import Path
from typing import List, Optional

from ..storage import JsonStore


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def canonical_json(payload) -> str:
    """JSON 规范化序列化（key 排序，保证相同内容哈希一致）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GenCache:
    """data/cache/ 下的 JSON 缓存仓（单用户本地，tmp+rename 原子写）。"""

    def __init__(self, data_dir: str):
        self.store = JsonStore(str(Path(data_dir) / "cache"))

    # ------------------------------------------------------------ key 构造

    @staticmethod
    def jd_key(jobs: List[dict], page_option: str, identity: str, jobs_rules_version: str) -> str:
        parts = ["jd", canonical_json(jobs), page_option, identity, jobs_rules_version]
        return _sha256("|".join(parts))

    @staticmethod
    def block_key(
        block: str,
        factsheet_version: str,
        rules_version: str,
        resume_input_hash: str,
    ) -> str:
        parts = ["block", block, factsheet_version, rules_version, resume_input_hash]
        return _sha256("|".join(parts))

    @staticmethod
    def resume_input_hash(resume_data: dict) -> str:
        """简历输入哈希：排除易变字段（id/createdAt/updatedAt/generation/direction），
        任何用户内容变更都会使板块缓存失效。"""
        volatile = {"id", "createdAt", "updatedAt", "generation", "direction", "contentPlan"}
        payload = {k: v for k, v in resume_data.items() if k not in volatile}
        return _sha256(canonical_json(payload))

    # ------------------------------------------------------------ 读写

    def get(self, key: str) -> Optional[dict]:
        data = self.store.load(key)
        return data or None

    def set(self, key: str, payload: dict) -> None:
        self.store.save(key, payload)

    def drop(self, key: str) -> bool:
        return self.store.delete(key)
