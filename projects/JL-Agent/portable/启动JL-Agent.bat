@echo off
rem ============================================================
rem  简历生成助手 Portable Launcher (no install, no Python required)
rem  Logic: try system Python first (run.py decides ABI/deps and
rem  falls back to the embedded runtime automatically), otherwise
rem  run with the bundled embedded Python (python\python.exe).
rem ============================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python run.py %*
    if %errorlevel%==0 exit /b 0
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run.py %*
    if %errorlevel%==0 exit /b 0
)

if exist "python\python.exe" (
    "python\python.exe" run.py %*
    exit /b %errorlevel%
)

echo.
echo [ERROR] No usable Python found.
echo         Install Python 3.10+ or check that "python\python.exe" exists in this folder.
pause
