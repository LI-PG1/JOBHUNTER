#!/usr/bin/env bash
# 面试跟踪助手启动器（macOS / Linux）
set -e
echo "=== 面试跟踪助手 - 启动器 ==="
echo

# [1] 环境检测
if ! command -v node >/dev/null 2>&1; then
  echo "[FAIL] 未检测到 Node.js。请先安装：brew install node（macOS）或 apt install nodejs（Ubuntu/Debian）"
  exit 1
fi

# [2] 配置生成
if [ ! -f config.json ] && [ -f config.example.json ]; then
  cp config.example.json config.json
  echo "[INFO] 已生成 config.json（默认端口 8902，可自行修改）"
fi

# [3] 一键自检
echo "[INFO] 运行环境自检..."
node server.js --selftest || { echo "[FAIL] 自检未通过，请按上方提示修复后重试"; exit 1; }

# [4] 启动服务
echo
echo "[INFO] 正在启动服务，请访问 http://127.0.0.1:8902"
echo "[INFO] 按 Ctrl+C 停止服务。"
echo
node server.js
