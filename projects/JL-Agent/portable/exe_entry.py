"""简历生成助手 EXE 入口（PyInstaller onefile 打包）。

特性：
  - 自包含：Python 解释器与全部依赖已打包进 EXE，无需外部环境；
  - 用户数据重定向：onefile 临时解压目录（sys._MEIPASS）每次运行会漂移，
    通过环境变量 JL_AGENT_DATA 将数据目录固定到 %LOCALAPPDATA%\\JL-Agent；
  - 端口自适应：8000 被占用自动顺延；
  - 自动打开浏览器工作台（控制台窗口保留为服务日志，关闭即退出）。
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

PORT_START = 8000
PORT_TRIES = 8
BROWSER_DELAY = 1.6  # 秒，等待服务就绪


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def appdata_dir() -> Path:
    """用户数据固定目录（EXE 场景）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(base) / "JL-Agent"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = Path.home() / "JL-Agent-data"
        d.mkdir(parents=True, exist_ok=True)
    return d


def pick_port(start=PORT_START, tries=PORT_TRIES):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def open_browser(url):
    def _go():
        time.sleep(BROWSER_DELAY)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


def main():
    if is_frozen():
        os.environ["JL_AGENT_DATA"] = str(appdata_dir())

    port = pick_port()
    url = "http://127.0.0.1:%d" % port
    print("=" * 56)
    print("  简历生成助手简历工作台")
    print("  服务地址：" + url)
    print("  浏览器将自动打开；关闭本窗口即退出服务。")
    print("=" * 56, flush=True)

    open_browser(url)

    from app.main import app  # 延迟导入：先完成环境变量注入
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
