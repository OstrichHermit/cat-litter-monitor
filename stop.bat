@echo off
chcp 65001 >nul
title 猫厕所监控系统 - 停止服务

echo.
echo ========================================
echo   猫厕所监控系统 - 停止中...
echo ========================================
echo.

cd /d "%~dp0"

echo [%time%] 开始关闭所有进程...

REM 1. 关闭 manager.py 进程（精确匹配 src\manager.py）
echo [1/3] 正在关闭 Manager 监控进程...
wmic process where "name='python.exe' and commandline like '%%src\\manager.py%%'" delete >nul 2>&1
if errorlevel 1 (
    echo       [提示] Manager 未运行或已关闭
) else (
    echo       [成功] Manager 已关闭
)

REM 2. 关闭 main.py 进程（精确匹配 src\main.py）
echo [2/3] 正在关闭主进程...
wmic process where "name='python.exe' and commandline like '%%src\\main.py%%'" delete >nul 2>&1
if errorlevel 1 (
    echo       [提示] 主进程未运行或已关闭
) else (
    echo       [成功] 主进程已关闭
)

REM 3. 关闭 go2rtc.exe 进程
echo [3/3] 正在关闭 go2rtc...
taskkill /F /IM go2rtc.exe >nul 2>&1
if errorlevel 1 (
    echo       [提示] go2rtc 未运行
) else (
    echo       [成功] go2rtc 已关闭
)

REM 等待进程完全关闭
echo.
echo 等待进程完全关闭...
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   所有服务已停止！
echo ========================================
echo.

timeout /t 1 /nobreak >nul
