@echo off
title 面试准备助手（纯文本版）一键启动
setlocal
rem 本文件位于发布包第一层，先进入工程文件目录
cd /d "%~dp0MS-Agent-Lite工程文件"
set PORT=8900
set "RUNTIME=%~dp0runtime"

echo ==================================================
echo   面试准备助手（纯文本版）一键启动器
echo   - 本地服务地址：http://127.0.0.1:%PORT%/
echo   - 数据仅保存在本机，请放心使用
echo ==================================================
echo.

rem ---------- 0) 内置运行时准备（首次启动自动解压，之后秒开） ----------
rem 0.1 Node.js：若 runtime\node\ 未解压且存在 node.zip，则自动解压
set "NODE_EXE="
if exist "%RUNTIME%\node\node.exe" (
    set "NODE_EXE=%RUNTIME%\node\node.exe"
) else if exist "%RUNTIME%\node.zip" (
    echo [0/4] 首次启动：正在解压内置 Node.js（约 20 秒，仅此一次）...
    powershell -NoProfile -Command "Expand-Archive -Path '%RUNTIME%\node.zip' -DestinationPath '%RUNTIME%' -Force" >nul
    if exist "%RUNTIME%\node-v24.19.0-win-x64\node.exe" (
        move /y "%RUNTIME%\node-v24.19.0-win-x64" "%RUNTIME%\node" >nul
    )
    if exist "%RUNTIME%\node\node.exe" set "NODE_EXE=%RUNTIME%\node\node.exe"
)

rem 0.2 依赖包：若 20_执行\node_modules 不存在且存在切片，则合并并解压
if not exist "%CD%\20_执行\node_modules" (
    if exist "%RUNTIME%\node_modules.zip.part1" (
        echo [1/4] 首次启动：正在解压内置依赖包（约 1 分钟，仅此一次）...
        powershell -NoProfile -Command "$fs=[System.IO.File]::Create('%RUNTIME%\node_modules.zip'); for($i=1;$i -le 3;$i++){ $p='%RUNTIME%\node_modules.zip.part'+$i; if(Test-Path $p){ $b=[System.IO.File]::ReadAllBytes($p); $fs.Write($b,0,$b.Length) } }; $fs.Close()" >nul
        powershell -NoProfile -Command "Expand-Archive -Path '%RUNTIME%\node_modules.zip' -DestinationPath '%CD%\20_执行' -Force" >nul
        del "%RUNTIME%\node_modules.zip" >nul 2>nul
    )
)

rem ---------- 1) 检查 Node.js（优先内置，其次系统） ----------
if not defined NODE_EXE (
    where node >nul 2>nul
    if errorlevel 1 (
        echo [错误] 未检测到 Node.js，发布包中也未找到内置运行时。
        echo.
        echo 解决办法：
        echo   1. 重新下载完整发布包（应包含 runtime 文件夹）
        echo   2. 或安装 Node.js LTS：https://nodejs.org
        echo.
        pause
        exit /b 1
    )
    set "NODE_EXE=node"
)
echo [2/4] Node.js 就绪

rem ---------- 2) 端口是否已被占用（服务可能已在运行） ----------
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 goto OPEN

rem ---------- 3) 后台启动服务（最小化窗口，便于日后关闭） ----------
echo [3/4] 正在启动本地服务，请稍候...
start "面试准备助手服务" /min "%NODE_EXE%" 20_执行\server.js

rem 轮询等待端口就绪（最多 20 秒）
set /a N=0
:WAIT
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>nul
if not errorlevel 1 goto OPEN
set /a N+=1
if %N% geq 20 goto FAIL
timeout /t 1 /nobreak >nul
goto WAIT

:FAIL
echo.
echo [错误] 服务启动失败或超时（20 秒）。可能原因：
echo   1. 端口 %PORT% 被其他程序占用 → 关闭占用程序后重试
echo   2. 20_执行\config.json 配置损坏 → 删除该文件后重试（会在网页重新配置）
echo   3. 内置依赖解压不完整 → 删除 20_执行\node_modules 后重新双击本文件（会重新解压）
echo   4. Node.js 版本过旧 → 请删除 runtime\node 后重新双击本文件（会重新解压内置版本）
echo.
echo   也可手动启动排查：在 20_执行 目录运行  node server.js
echo.
pause
exit /b 1

:OPEN
echo [4/4] 服务已就绪，正在打开浏览器...
start "" "http://127.0.0.1:%PORT%/"
echo.
echo 已自动打开浏览器；如未打开，请手动访问：http://127.0.0.1:%PORT%/
echo.
echo 使用完可在任务栏找到"面试准备助手服务"最小化窗口并关闭它来停止服务。
echo （关闭本窗口不影响服务运行）
echo.
timeout /t 8 /nobreak >nul
exit /b 0
