@echo off
chcp 65001 >nul
title CatLitterMonitor - Restart

echo.
echo ========================================
echo   CatLitterMonitor - Restarting...
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

echo [%time%] Stopping business processes...

REM Kill all cat-litter-monitor processes except manager
python "%~dp0scripts\kill_monitor.py" manager >nul 2>&1

REM Kill go2rtc
taskkill /F /IM go2rtc.exe >nul 2>&1

echo       Business processes stopped (Manager keeps running)

echo.
echo Waiting for processes to exit...
timeout /t 2 /nobreak >nul

echo.
echo [%time%] Starting business services...

echo [1/3] Starting go2rtc...
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
timeout /t 3 /nobreak >nul

echo [2/3] Starting Main...
start "" /b "%PYTHONW%" "%~dp0src\main.py"

timeout /t 1 /nobreak >nul

echo [3/3] Starting MCP Server...
start "" /b "%PYTHONW%" "%~dp0src\mcp\server.py"

echo.
echo ========================================
echo   Restart complete!
echo ========================================
echo.
echo Business services restarted (Manager keeps running)
echo.
