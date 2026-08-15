"""插件注册表与运行状态：驱动悬浮控制台「一键配置 / 一键卸载」双按钮。

组件清单（含灰区/非官方源，方案 v0.5 §4.2 有限授权）：
- ddgs        DuckDuckGo 免 Key 搜索增强（pip duckduckgo-search）
- trafilatura 本地网页正文提取（pip trafilatura）
- playwright  无头浏览器兜底（pip playwright + chromium，~150MB，需用户确认）
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from ..config import BASE_DIR, config

VENV_PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
VENV_PIP = BASE_DIR / ".venv" / "Scripts" / "pip.exe"

COMPONENTS: dict[str, dict] = {
    "ddgs": {
        "name": "DuckDuckGo 免 Key 搜索",
        "pip": [],
        "size": "内置（免安装）",
        "import": "__self_impl__",  # 搜索插件内自实现 HTML 解析，无需 pip 包
        "gray": True,  # 非官方源，有限授权
        "self_impl": True,
    },
    "trafilatura": {
        "name": "Trafilatura 正文提取",
        "pip": ["trafilatura"],
        "size": "小",
        "import": "trafilatura",
        "gray": False,
    },
    "playwright": {
        "name": "Playwright 无头浏览器（兜底）",
        "pip": ["playwright"],
        "browser": "chromium",
        "size": "大（~150MB）",
        "import": "playwright",
        "gray": False,
        "confirm": True,  # 需用户确认下载
    },
}


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _check_import(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:  # noqa: BLE001
        return False


def _pip() -> str:
    return str(VENV_PIP if VENV_PIP.exists() else "pip")


class PluginManager:
    """插件状态机：一键配置 / 一键卸载（互斥，运行中锁定）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.busy: str | None = None  # None / "configuring" / "uninstalling"
        self.progress: str = "空闲"
        self.updated = threading.Event()

    # ---------- 状态 ----------

    def status(self) -> dict:
        comps: dict[str, dict] = {}
        for cid, comp in COMPONENTS.items():
            comps[cid] = {
                "name": comp["name"],
                "size": comp["size"],
                "gray": comp.get("gray", False),
                "installed": True if comp.get("self_impl") else _check_import(comp["import"]),
                "enabled": bool(config.plugins_state.get(cid, {}).get("enabled", True)),
            }
        return {
            "busy": self.busy,
            "progress": self.progress,
            "components": comps,
            "search_chain": config.plugins_state.get("search_chain", "自动探测"),
        }

    def _set_progress(self, msg: str) -> None:
        self.progress = msg
        self.updated.set()

    # ---------- 配置（cid=None 全部） ----------

    def _configure_one(self, cid: str, cb: Callable[[str], None]) -> str:
        comp = COMPONENTS[cid]
        if comp.get("confirm"):
            cb(f"跳过 {comp['name']}（需用户确认，可单独安装）")
            return "skipped"
        if comp.get("self_impl"):
            config.plugins_state[cid] = {"enabled": True, "installed": True}
            return "already"
        cb(f"配置 {comp['name']}...")
        if _check_import(comp["import"]):
            code, out = self._ensure_browser(comp, cb)
            if code != 0:
                return f"failed: {out[-200:]}"
            config.plugins_state[cid] = {"enabled": True, "installed": True}
            return "already"
        code, out = _run([_pip(), "install", "-q"] + comp["pip"])
        if code == 0 and _check_import(comp["import"]):
            code, out = self._ensure_browser(comp, cb)
            if code != 0:
                return f"failed: {out[-200:]}"
            config.plugins_state[cid] = {"enabled": True, "installed": True}
            return "installed"
        cb(f"⚠️ {comp['name']} 安装失败，将自动降级")
        return f"failed: {out[-200:]}"

    @staticmethod
    def _ensure_browser(comp: dict, cb: Callable[[str], None]) -> tuple[int, str]:
        """有 browser 声明的组件（playwright）额外下载无头浏览器内核。"""
        browser = comp.get("browser")
        if not browser:
            return 0, ""
        cb(f"下载 {comp['name']} 浏览器内核（{comp.get('size', '')}）...")
        return _run([sys.executable, "-m", "playwright", "install", browser], timeout=1800)

    def _refresh_chain(self, cb: Callable[[str], None]) -> None:
        cb("自检搜索通道...")
        try:
            from .search import search_plugin
            search_plugin.refresh()
            chain = " → ".join(search_plugin.active_chain())
            config.plugins_state["search_chain"] = chain
            cb(f"搜索通道就绪：{chain}")
        except Exception as exc:  # noqa: BLE001
            config.plugins_state["search_chain"] = f"异常: {exc}"

    def configure(self, cid: str | None = None, progress_cb: Callable[[str], None] | None = None) -> dict:
        if cid is not None and cid not in COMPONENTS:
            return {"ok": False, "error": f"未知插件：{cid}"}
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": "插件操作进行中，请稍候"}
        self.busy = "configuring"
        try:
            cb = progress_cb or self._set_progress
            if getattr(sys, "frozen", False):
                # 打包版：无法 pip 安装组件，内置 ddgs/urllib 通道可用
                cb("打包版已内置 DuckDuckGo/urllib 搜索通道，扩展组件请使用源码运行")
                config.plugins_state = {}
                config.save()
                return {cid or "all": "frozen_unsupported"}
            cb("开始配置...")
            ids = [cid] if cid else list(COMPONENTS)
            results: dict[str, str] = {}
            for i in ids:
                results[i] = self._configure_one(i, cb)
            self._refresh_chain(cb)
            config.save()
            cb("配置完成")
            return {"ok": True, "results": results, "chain": config.plugins_state.get("search_chain")}
        finally:
            self.busy = None
            self._lock.release()

    # ---------- 卸载（cid=None 全部） ----------

    def _uninstall_one(self, cid: str, cb: Callable[[str], None]) -> str:
        comp = COMPONENTS[cid]
        if comp.get("self_impl"):
            return "self_impl"
        if not _check_import(comp["import"]):
            return "not_installed"
        cb(f"卸载 {comp['name']}...")
        code, _ = _run([_pip(), "uninstall", "-y", "-q"] + comp["pip"])
        return "uninstalled" if code == 0 else "failed"

    def uninstall(self, cid: str | None = None, progress_cb: Callable[[str], None] | None = None) -> dict:
        if cid is not None and cid not in COMPONENTS:
            return {"ok": False, "error": f"未知插件：{cid}"}
        if not self._lock.acquire(blocking=False):
            return {"ok": False, "error": "插件操作进行中，请稍候"}
        self.busy = "uninstalling"
        try:
            cb = progress_cb or self._set_progress
            cb("开始卸载...")
            ids = [cid] if cid else list(COMPONENTS)
            results: dict[str, str] = {}
            for i in ids:
                results[i] = self._uninstall_one(i, cb)
            # 清理配置（单插件只清自身，全部则重置）
            if cid is None:
                config.plugins_state = {}
            else:
                config.plugins_state.pop(cid, None)
            config.save()
            try:
                from .search import search_plugin
                search_plugin.refresh()
            except Exception:  # noqa: BLE001
                pass
            cb("卸载完成")
            return {"ok": True, "results": results}
        finally:
            self.busy = None
            self._lock.release()


plugin_manager = PluginManager()
