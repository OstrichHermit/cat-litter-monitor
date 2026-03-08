@echo off
chcp 65001 >nul
title 猫厕所监控系统

echo.
echo ========================================
echo   猫厕所监控系统 - 启动中...
echo ========================================
echo.

cd /d "%~dp0"

REM 设置进程名称前缀，便于识别和关闭
set PROCESS_PREFIX=CatLitterMonitor

REM 创建日志目录
if not exist "logs" mkdir logs

REM 启动 go2rtc
echo [%time%] 正在启动 go2rtc...
start "%PROCESS_PREFIX%-go2rtc" /MIN "D:\AgentWorkspace\go2rtc\go2rtc.exe" -c "D:\AgentWorkspace\go2rtc\go2rtc.yaml"
if errorlevel 1 (
    echo [错误] go2rtc 启动失败
    pause
    exit /b 1
)
echo [成功] go2rtc 已启动

REM 等待 go2rtc 完全启动
echo 等待 go2rtc 初始化...
timeout /t 3 /nobreak >nul

REM 启动主进程
echo [%time%] 正在启动主进程...
start "%PROCESS_PREFIX%-Main" cmd /c "python src\main.py"
if errorlevel 1 (
    echo [错误] 主进程启动失败
    pause
    exit /b 1
)
echo [成功] 主进程已启动

REM 等待主进程初始化
echo 等待主进程初始化...
timeout /t 2 /nobreak >nul

REM 启动 manager 监控进程
echo [%time%] 正在启动 manager 监控进程...
start "%PROCESS_PREFIX%-Manager" /MIN cmd /c "python src\manager.py"
if errorlevel 1 (
    echo [错误] manager 启动失败
    pause
    exit /b 1
)
echo [成功] manager 已启动

echo.
echo ========================================
echo   所有服务已启动！
echo ========================================
echo.
echo 提示：
echo - go2rtc 窗口：最小化运行
echo - 主进程窗口：显示系统运行状态
echo - Manager 窗口：最小化运行，监控系统状态
echo.
echo 关闭系统请运行 stop.bat 或按 Ctrl+C
echo.

REM 等待任意键退出
echo 按任意键关闭此窗口（不影响服务运行）...
pause >nul
