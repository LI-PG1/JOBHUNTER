"""tracker_agent：投递/面试记录本地存储组件（N10）。

大脑节点进程内调用：`TrackerStore().append(records)`。
"""
from tracker_agent.store import TrackerStore

__all__ = ["TrackerStore"]
