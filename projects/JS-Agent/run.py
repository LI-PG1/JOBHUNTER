"""JS-Agent 一键启动（跨平台）。

用法：
    python run.py                # 使用默认端口（见 config.json / 默认 8101）
    python run.py --port 8102    # 自定义端口
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    # Windows 控制台默认 GBK：切 UTF-8 保证中文 banner 不乱码
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    parser = argparse.ArgumentParser(description="JS-Agent 岗位匹配助手")
    parser.add_argument("--host", default=None, help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认 8101）")
    args = parser.parse_args()

    print("=" * 56)
    print("  JS-Agent 岗位匹配助手 v0.2（LLM-Agent 版）")
    print("  使用：浏览器打开页面 → 控制台配置大模型 API Key → 填写画像 → 执行匹配")
    print("  免责声明：搜索通道含非官方源（DuckDuckGo 等），仅供个人学习，请勿滥用")
    print("=" * 56)

    import uvicorn

    from app.config import config

    host = args.host or config.host
    port = args.port or config.port
    print(f"  启动服务：http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
