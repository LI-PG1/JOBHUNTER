@echo off
rem JS-Agent 一键启动（Windows）
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe run.py %*
) else (
    python run.py %*
)
pause
