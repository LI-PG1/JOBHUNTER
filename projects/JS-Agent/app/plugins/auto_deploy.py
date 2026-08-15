"""插件自动部署入口：后台线程执行「配置 / 卸载」（cid=None 为全部），供控制台 API 调用。

交互（方案 v0.5 §4.3）：操作期间按钮置灰，实时状态「配置中...」，完成后恢复。
"""
from __future__ import annotations

import threading
from typing import Callable

from .registry import plugin_manager


def start_configure(cid: str | None = None, cb: Callable[[str], None] | None = None) -> bool:
    """后台启动配置（单插件或全部）。已在运行返回 False。"""
    if plugin_manager.busy is not None:
        return False
    t = threading.Thread(target=plugin_manager.configure, args=(cid, cb), daemon=True)
    t.start()
    return True


def start_uninstall(cid: str | None = None, cb: Callable[[str], None] | None = None) -> bool:
    """后台启动卸载（单插件或全部）。已在运行返回 False。"""
    if plugin_manager.busy is not None:
        return False
    t = threading.Thread(target=plugin_manager.uninstall, args=(cid, cb), daemon=True)
    t.start()
    return True
