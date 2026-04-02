@echo off
chcp 65001 >nul
title CatLitterMonitor

echo.
echo ========================================
echo   CatLitterMonitor - Starting...
echo ========================================
echo.

cd /d "%~dp0"

:: ===== go2rtc 路径配置（可按需修改）=====
:: 默认值：go2rtc 位于项目同级目录下
set "GO2RTC_PATH=%~dp0..\go2rtc\go2rtc.exe"
set "GO2RTC_CONFIG=%~dp0..\go2rtc\go2rtc.yaml"
:: =========================================

set PROCESS_PREFIX=CatLitterMonitor

if not exist "logs" mkdir logs

echo. > logs\go2rtc.log
echo. > logs\main.log
echo. > logs\manager.log
echo. > logs\mcp.log

echo [%time%] Starting go2rtc...
if not exist "%GO2RTC_PATH%" (
    echo [ERROR] go2rtc not found: %GO2RTC_PATH%
    echo         Please modify GO2RTC_PATH in this script or copy go2rtc to the correct location.
    pause
    exit /b 1
)
if not exist "%GO2RTC_CONFIG%" (
    echo [WARNING] go2rtc config not found: %GO2RTC_CONFIG%
)
powershell -Command "Start-Process cmd.exe -ArgumentList '/c %GO2RTC_PATH% -c %GO2RTC_CONFIG% >> %CD%\logs\go2rtc.log 2>&1' -WindowStyle Hidden"
if errorlevel 1 (
    echo [ERROR] go2rtc failed to start
    pause
    exit /b 1
)
echo [OK] go2rtc started

echo Waiting for go2rtc...
timeout /t 3 /nobreak >nul

echo [%time%] Starting main...
start "%PROCESS_PREFIX%-Main" /B pythonw "%~dp0src\main.py"
if errorlevel 1 (
    echo [ERROR] main failed to start
    pause
    exit /b 1
)
echo [OK] main started

echo Waiting for main...
timeout /t 2 /nobreak >nul

echo [%time%] Starting manager...
start "%PROCESS_PREFIX%-Manager" /B pythonw "%~dp0src\manager.py"
if errorlevel 1 (
    echo [ERROR] manager failed to start
    pause
    exit /b 1
)
echo [OK] manager started

echo [%time%] Starting MCP Server...
start "%PROCESS_PREFIX%-MCP" /B pythonw "%~dp0src\mcp\server.py"
if errorlevel 1 (
    echo [ERROR] MCP Server failed to start
    pause
    exit /b 1
)
echo [OK] MCP Server started

echo.
echo ========================================
echo   All services started! (background)
echo ========================================
echo.
echo Logs: logs\go2rtc.log  logs\main.log  logs\manager.log  logs\mcp.log
echo Web: http://localhost:5000
echo Stop: run stop.bat
echo.

timeout /t 1 /nobreak >nul
