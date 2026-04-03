@echo off
chcp 65001 >nul
title CatLitterMonitor - Stop

echo.
echo ========================================
echo   CatLitterMonitor - Stopping...
echo ========================================
echo.

cd /d "%~dp0"

echo [%time%] Stopping all processes...

REM Kill all cat-litter-monitor processes (including manager, for full stop)
python "%~dp0scripts\kill_monitor.py"
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
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   All services stopped!
echo ========================================
echo.

timeout /t 1 /nobreak >nul
