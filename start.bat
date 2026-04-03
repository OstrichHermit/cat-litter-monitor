@echo off
chcp 65001 >nul
title CatLitterMonitor

echo.
echo ========================================
echo   CatLitterMonitor - Starting...
echo ========================================
echo.

cd /d "%~dp0"

REM ===== go2rtc 路径配置（可按需修改）=====
set "GO2RTC_PATH=%~dp0..\go2rtc\go2rtc.exe"
set "GO2RTC_CONFIG=%~dp0..\go2rtc\go2rtc.yaml"
REM =========================================

REM Find Python executable
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable.replace('\\python.exe','\\pythonw.exe'))" 2^>nul') do set PYTHONW=%%i
if not defined PYTHONW set PYTHONW=pythonw.exe

if not exist "logs" mkdir logs

echo [%time%] Starting go2rtc...
if not exist "%GO2RTC_PATH%" (
    echo [ERROR] go2rtc not found: %GO2RTC_PATH%
    echo         Please modify GO2RTC_PATH in this script.
    pause
    exit /b 1
)
if not exist "%GO2RTC_CONFIG%" (
    echo [WARNING] go2rtc config not found: %GO2RTC_CONFIG%
)
powershell -Command "Start-Process cmd.exe -ArgumentList '/c %GO2RTC_PATH% -c %GO2RTC_CONFIG% >> %CD%\logs\go2rtc.log 2>&1' -WindowStyle Hidden"
echo [OK] go2rtc started

echo Waiting for go2rtc...
timeout /t 3 /nobreak >nul

echo [%time%] Starting main...
start "" /b "%PYTHONW%" "%~dp0src\main.py"
echo [OK] main started

timeout /t 1 /nobreak >nul

echo [%time%] Starting manager...
start "" /b "%PYTHONW%" "%~dp0src\manager.py"
echo [OK] manager started

timeout /t 1 /nobreak >nul

echo [%time%] Starting MCP Server...
start "" /b "%PYTHONW%" "%~dp0src\mcp\server.py"
echo [OK] MCP Server started

echo.
echo ========================================
echo   All services started! (background)
echo ========================================
echo.
echo Web: http://localhost:5000
echo Stop: run stop.bat
echo.

timeout /t 1 /nobreak >nul
