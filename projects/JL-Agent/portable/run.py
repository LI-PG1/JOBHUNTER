"""简历生成助手便携版启动器（跨解释器，平台：Windows 为主）。

职责（对应分发方案 4 层解释器决策）：
  1) 若当前已运行在内置嵌入式 Python 上 → 直接启动应用；
  2) 若系统 Python 主次版本与内置依赖 ABI 一致（3.12）→ 直接运行，
     并通过 sys.path 注入包内依赖（不 pip install、不污染系统环境）；
  3) 若系统 Python 版本不匹配（3.10/3.11/3.13…）→ 自动重启到内置嵌入式 Python；
  4) 无系统 Python → bat 入口直接用内置嵌入式 Python 运行本文件。

嵌入式运行时首次使用复制到 %TEMP%\\JL-Agent-runtime\\python（免二次解压、不占安装目录）。

用法（双击 启动JL-Agent.bat 或命令行）：
    python run.py [--port 8000] [--no-browser]
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
EMBED_DIR = os.path.join(BASE, "python")            # 内置嵌入式运行时（随 ZIP 分发）
EMBED_EXE = os.path.join(EMBED_DIR, "python.exe")
SITE = os.path.join(EMBED_DIR, "Lib", "site-packages")  # 共享依赖（cp312 轮子）
ABI = (3, 12)                                        # 内置依赖的 CPython ABI（构建时固定）
APP = "app.main:app"
HOST = "127.0.0.1"

# 启动依赖探测清单（任一缺失则视为系统环境不可复用）
DEPS = ["fastapi", "uvicorn", "pydantic", "httpx", "PIL", "docx", "jsonschema", "multipart"]


def log(msg):
    print("[简历生成助手] " + msg, flush=True)


def is_embed():
    """当前解释器是否为内置嵌入式 Python。"""
    exe = os.path.normpath(sys.executable)
    return exe.startswith(os.path.normpath(EMBED_DIR)) or "JL-Agent-runtime" in exe


def inject_site():
    """把包内依赖注入 sys.path（对系统 Python 生效；嵌入式下 _pth 已包含，重复无害）。"""
    if os.path.isdir(SITE) and SITE not in sys.path:
        sys.path.insert(0, SITE)


def deps_ok(python_exe, env):
    """探测解释器能否 import 全部启动依赖。"""
    code = ("import importlib;" +
            "mods=%r;" % DEPS +
            "import sys; sys.exit(0 if all(importlib.import_module(m) for m in mods) else 1)")
    try:
        r = subprocess.run([python_exe, "-c", code], capture_output=True, text=True,
                           timeout=120, env=env)
        return r.returncode == 0
    except Exception:
        return False


def pick_port(start=8000, tries=6):
    """从 start 起找一个空闲端口。"""
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    return start


def find_system_python_312():
    """扫描系统 Python：优先 py launcher（py -3.12），其次 PATH 中的 python/python3。
    要求版本 == 内置 ABI（3.12），确保可复用包内 cp312 轮子。"""
    candidates = []
    for launcher_ver in ("3.12", "-3.12", ""):
        if launcher_ver == "":
            candidates.append(["py", "-3"])
        else:
            candidates.append(["py", launcher_ver])
    candidates += [["python"], ["python3"]]
    seen = set()
    for cand in candidates:
        try:
            r = subprocess.run(cand + ["-c", "import sys;print(sys.executable, sys.version_info[0], sys.version_info[1])"],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode != 0:
            continue
        m = re.match(r"(\S+)\s+(\d+)\s+(\d+)", (r.stdout or "").strip())
        if not m:
            continue
        exe, maj, minor = m.group(1), int(m.group(2)), int(m.group(3))
        key = exe.lower()
        if key in seen:
            continue
        seen.add(key)
        if (maj, minor) == ABI:
            return exe
    return None


def ensure_embed_runtime():
    """把内置嵌入式运行时复制到 %TEMP%\\JL-Agent-runtime\\python（存在则跳过），返回其 python.exe。
    临时目录不可用时回退到直接使用包内运行时。"""
    if not os.path.isfile(EMBED_EXE):
        return None
    try:
        tmp = os.path.join(tempfile.gettempdir(), "JL-Agent-runtime")
        dst = os.path.join(tmp, "python")
        if not os.path.isfile(os.path.join(dst, "python.exe")):
            log("首次运行：解压内置运行时到临时目录（%s）…" % dst)
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(EMBED_DIR, dst, ignore=shutil.ignore_patterns("__pycache__"))
        return os.path.join(dst, "python.exe")
    except Exception as e:
        log("临时目录不可用（%s），直接使用包内运行时。" % e)
        return EMBED_EXE


def open_browser(url, delay=1.4):
    def _go():
        time.sleep(delay)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_go, daemon=True).start()


def restart_with(python_exe, args):
    """用目标解释器重启本启动器（版本不匹配时切到嵌入式）。"""
    log("切换到内置运行时：" + python_exe)
    try:
        os.execv(python_exe, [python_exe] + sys.argv)
    except OSError:
        subprocess.run([python_exe] + sys.argv, cwd=BASE, check=True)


def run_app(python_exe=None, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    port = pick_port()
    url = "http://%s:%d" % (HOST, port)
    log("正在启动简历生成助手 → " + url)
    if "--no-browser" not in sys.argv:
        open_browser(url)
    cmd = [python_exe or sys.executable, "-m", "uvicorn", APP,
           "--host", HOST, "--port", str(port)]
    log("执行：" + " ".join(cmd))
    subprocess.run(cmd, cwd=BASE, env=env)


def main():
    # 1) 当前已是内置嵌入式 → 直接跑
    if is_embed():
        inject_site()
        return run_app()

    inject_site()
    # 2) 当前系统 Python 版本 == 内置 ABI 且依赖齐全 → 直接跑（依赖已注入）
    if sys.version_info[:2] == ABI and deps_ok(sys.executable, dict(os.environ)):
        return run_app()

    # 3) 系统存在 3.12 的 Python（当前解释器不符时）→ 切过去
    sys312 = find_system_python_312()
    if sys312:
        env = dict(os.environ)
        env["PYTHONPATH"] = SITE + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        if deps_ok(sys312, env):
            return run_app(python_exe=sys312, extra_env=env)
        return restart_with(sys312, sys.argv)

    # 4) 兜底：内置嵌入式（复制到临时目录后运行）
    embed = ensure_embed_runtime()
    if embed:
        return restart_with(embed, sys.argv)

    log("错误：未找到可用的 Python 环境。请安装 Python 3.10+ 或确认包内 python 目录完整。")
    sys.exit(1)


if __name__ == "__main__":
    main()
