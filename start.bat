@echo off
chcp 65001 >nul
title 猫厕所监控系统

echo.
echo ========================================
echo   猫厕所监控系统 - 启动中...
echo ========================================
echo.

cd /d "%~dp0"

python src\main.py

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出
    pause
)
