"""规则文件加载：jsonschema 校验 + 版本记录（契约 §2/§3.3）。"""
import hashlib
import json
from pathlib import Path

import jsonschema

from .errors import AppError, E_RULES_MISSING


class RulesLoader:
    """加载 rules/ 下全部规则文件，schema 校验失败即启动报错（fail fast）。"""

    def __init__(self, rules_dir: str):
        self.root = Path(rules_dir)
        self.schema_dir = self.root / "schema"
        self.versions: dict[str, str] = {}
        self._data: dict = {}

    def load_all(self) -> None:
        self._load_industries()
        self._load("projects", "mapping.json")
        self._load("skills", "rules.json")
        self._load("jobs", "rules.json")

    def _validate(self, kind: str, payload: dict) -> None:
        schema_path = self.schema_dir / f"{kind}.schema.json"
        if schema_path.exists():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(payload, schema)

    def _load(self, kind: str, filename: str) -> None:
        path = self.root / kind / filename
        if not path.exists():
            raise AppError(E_RULES_MISSING, f"规则文件缺失: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._validate(kind, payload)
        self._data[kind] = payload
        self.versions[kind] = hashlib.sha1(path.read_bytes()).hexdigest()[:8]

    def _load_industries(self) -> None:
        indir = self.root / "industries"
        entries = {}
        for f in sorted(indir.glob("*.json")):
            payload = json.loads(f.read_text(encoding="utf-8"))
            self._validate("industry", payload)
            entries[payload["industry"]] = payload
        self._data["industries"] = entries
        self.versions["industries"] = ",".join(sorted(entries.keys()))

    # ---- 访问器 ----
    def industry(self, name: str):
        return self._data["industries"].get(name)

    def industries(self) -> dict:
        return self._data["industries"]

    def projects_mapping(self) -> dict:
        return self._data["projects"]

    def skills_rules(self) -> dict:
        return self._data["skills"]

    def jobs_rules(self) -> dict:
        return self._data["jobs"]
