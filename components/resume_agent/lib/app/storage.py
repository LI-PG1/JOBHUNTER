"""本地 JSON 持久化（契约 §1 存储形态）：resumes / tasks / photos。

单用户本地运行，无并发控制；写入采用 tmp+rename 原子替换防止半写文件。
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .core.errors import AppError, E_TASK_NOT_FOUND


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"


class JsonStore:
    """按 id 存储 dict 的通用 JSON 文件仓。"""

    def __init__(self, directory: str):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def save(self, key: str, payload: dict) -> None:
        path = self._path(key)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def load(self, key: str, not_found_code: Optional[int] = None, label: str = "记录") -> dict:
        path = self._path(key)
        if not path.exists():
            if not_found_code is not None:
                raise AppError(not_found_code, f"{label}不存在: {key}", {"id": key})
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list(self) -> List[str]:
        return sorted(p.stem for p in self.dir.glob("*.json") if not p.name.endswith(".tmp"))


class Storage:
    """简历生成助手本地数据仓（resumes / tasks / photos）。"""

    def __init__(self, data_dir: str):
        self.root = Path(data_dir)
        self.resumes = JsonStore(str(self.root / "resumes"))
        self.tasks = JsonStore(str(self.root / "tasks"))
        self.photos_dir = self.root / "photos"
        self.photos_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------ Resume
    def new_resume_id(self) -> str:
        return _new_id("res")

    def save_resume(self, resume: dict) -> None:
        self.resumes.save(resume["id"], resume)

    def load_resume(self, resume_id: str) -> dict:
        return self.resumes.load(resume_id, 40008, "简历")

    def delete_resume(self, resume_id: str) -> bool:
        return self.resumes.delete(resume_id)

    def list_resumes(self) -> List[str]:
        return self.resumes.list()

    # ------------------------------------------------------------ Task
    def new_task_id(self) -> str:
        return _new_id("task")

    def save_task(self, task: dict) -> None:
        self.tasks.save(task["id"], task)

    def load_task(self, task_id: str) -> dict:
        return self.tasks.load(task_id, E_TASK_NOT_FOUND, "任务")

    # ------------------------------------------------------------ Photo
    def save_photo(self, photo_id: str, data: bytes, fmt: str) -> str:
        """保存照片二进制，返回相对路径（如 data/photos/{id}.jpg）。"""
        path = self.photos_dir / f"{photo_id}.{fmt}"
        path.write_bytes(data)
        return str(Path("data") / "photos" / path.name)

    # ------------------------------------------------------------ Settings（§5 设置控制台）
    _DEFAULT_SETTINGS = {
        "apiKey": "",
        "searchApiKey": "",
        "deepSearchDefault": True,
        "watermarkDefault": "formal",
        "providers": [],
        "activeProviderId": "",
        "pluginsEnabled": {},
        "pluginState": {},    # {plugin_id: {configured, installStatus, installMsg, config, features{}}}
    }

    def load_settings(self) -> dict:
        path = self.root / "settings.json"
        if not path.exists():
            return dict(self._DEFAULT_SETTINGS)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return dict(self._DEFAULT_SETTINGS)
        merged = dict(self._DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in merged})
        return merged

    def save_settings(self, settings: dict) -> None:
        path = self.root / "settings.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def photo_to_data_url(file_path: str) -> str:
        """读取照片文件并编码为 data URL（供预览与模板注入）。"""
        from base64 import b64encode

        path = Path(file_path)
        if not path.exists():
            return ""
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64,{b64encode(path.read_bytes()).decode()}"

    @staticmethod
    def new_photo_id() -> str:
        return _new_id("ph")
