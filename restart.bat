@echo off
chcp 65001 >nul
title CatLitterMonitor - Restart

echo.
echo ========================================
echo   CatLitterMonitor - Restarting...
echo ========================================
echo.

cd /d "%~dp0"

echo [%time%] Stopping business processes...

echo [1/2] Stopping Main...
wmic process where "(name='python.exe' or name='pythonw.exe') and commandline like '%%cat-litter-monitor%%main.py%%'" delete >nul 2>&1

echo [2/2] Stopping go2rtc...
taskkill /F /IM go2rtc.exe >nul 2>&1

echo       Business processes stopped (Manager keeps running)

echo.
echo Waiting for processes to exit...
timeout /t 3 /nobreak >nul

echo.
echo [%time%] Starting business services...

echo [1/2] Starting go2rtc...
powershell -Command "Start-Process cmd.exe -ArgumentList '/c D:\AgentWorkspace\go2rtc\go2rtc.exe -c D:\AgentWorkspace\go2rtc\go2rtc.yaml >> %CD%\logs\go2rtc.log 2>&1' -WindowStyle Hidden"

timeout /t 3 /nobreak >nul

echo [2/2] Starting main...
start "CatLitterMonitor-Main" /B pythonw "%~dp0src\main.py"

echo.
echo ========================================
echo   Restart complete!
echo ========================================
echo.
echo Business services restarted (Manager keeps running)
echo.
