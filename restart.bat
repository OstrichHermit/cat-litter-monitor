@echo off
chcp 65001 >nul
title 猫厕所监控系统 - 重启服务

echo.
echo ========================================
echo   猫厕所监控系统 - 重启中...
echo ========================================
echo.

cd /d "%~dp0"

echo [%time%] 开始关闭业务进程...

REM 1. 关闭 main.py 进程（精确匹配 src\main.py）
echo [1/2] 正在关闭主进程...
wmic process where "name='python.exe' and commandline like '%%src\\main.py%%'" delete >nul 2>&1

REM 2. 关闭 go2rtc.exe 进程
echo [2/2] 正在关闭 go2rtc...
taskkill /F /IM go2rtc.exe >nul 2>&1

echo       业务进程已关闭（Manager 保持运行）

REM 等待进程完全关闭
echo.
echo 等待进程完全关闭...
timeout /t 3 /nobreak >nul

echo.
echo [%time%] 开始启动业务服务...

REM 1. 启动 go2rtc
echo [1/2] 正在启动 go2rtc...
start "CatLitterMonitor-go2rtc" /MIN "D:\AgentWorkspace\go2rtc\go2rtc.exe" -c "D:\AgentWorkspace\go2rtc\go2rtc.yaml"

REM 等待 go2rtc 完全启动
timeout /t 3 /nobreak >nul

REM 2. 启动主进程
echo [2/2] 正在启动主进程...
start "CatLitterMonitor-Main" cmd /k python src\main.py

echo.
echo ========================================
echo   重启完成！
echo ========================================
echo.
echo 业务服务已重新启动（Manager 保持运行）
echo.
