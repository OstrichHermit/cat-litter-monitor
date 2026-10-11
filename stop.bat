@echo off
chcp 65001 >nul
title CatLitterMonitor - Stop

echo.
echo ========================================
echo   CatLitterMonitor - Stopping...
echo ========================================
echo.

cd /d "%~dp0"

REM Find Python executable
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set PYTHON=%%i
if not defined PYTHON set PYTHON=python

echo [%time%] Stopping all processes...

REM Kill all cat-litter-monitor processes (including manager, for full stop)
"%PYTHON%" "%~dp0scripts\kill_monitor.py"
if errorlevel 1 (
    echo       [INFO] No processes running
) else (
    echo       [OK] Processes stopped
)

REM Kill go2rtc
taskkill /F /IM go2rtc.exe >nul 2>&1
if errorlevel 1 (
    echo       [INFO] go2rtc not running
) else (
    echo       [OK] go2rtc stopped
)

echo.
echo Waiting for processes to exit...
ping -n 3 127.0.0.1 >nul

echo.
echo ========================================
echo   All services stopped!
echo ========================================
echo.

ping -n 2 127.0.0.1 >nul
