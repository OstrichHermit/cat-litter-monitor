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

echo [1/3] Stopping Manager...
wmic process where "(name='python.exe' or name='pythonw.exe') and commandline like '%%cat-litter-monitor%%manager.py%%'" delete >nul 2>&1
if errorlevel 1 (
    echo       [INFO] Manager not running
) else (
    echo       [OK] Manager stopped
)

echo [2/3] Stopping Main...
wmic process where "(name='python.exe' or name='pythonw.exe') and commandline like '%%cat-litter-monitor%%main.py%%'" delete >nul 2>&1
if errorlevel 1 (
    echo       [INFO] Main not running
) else (
    echo       [OK] Main stopped
)

echo [3/3] Stopping go2rtc...
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
