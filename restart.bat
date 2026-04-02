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

echo [1/3] Stopping Main...
wmic process where "(name='python.exe' or name='pythonw.exe') and commandline like '%%cat-litter-monitor%%main.py%%'" delete >nul 2>&1

echo [2/3] Stopping MCP Server...
wmic process where "(name='python.exe' or name='pythonw.exe') and commandline like '%%cat-litter-monitor%%mcp%%server%%'" delete >nul 2>&1

echo [3/3] Stopping go2rtc...
taskkill /F /IM go2rtc.exe >nul 2>&1

echo       Business processes stopped (Manager keeps running)

echo.
echo Waiting for processes to exit...
timeout /t 3 /nobreak >nul

echo.
echo [%time%] Starting business services...

echo [1/3] Starting go2rtc...
powershell -Command "Start-Process cmd.exe -ArgumentList '/c D:\AgentWorkspace\go2rtc\go2rtc.exe -c D:\AgentWorkspace\go2rtc\go2rtc.yaml >> %CD%\logs\go2rtc.log 2>&1' -WindowStyle Hidden"

timeout /t 3 /nobreak >nul

echo [2/3] Starting Main...
start "CatLitterMonitor-Main" /B pythonw "%~dp0src\main.py"

timeout /t 2 /nobreak >nul

echo [3/3] Starting MCP Server...
start "CatLitterMonitor-MCP" /B pythonw "%~dp0src\mcp\server.py" --transport http --host 127.0.0.1 --port 5001

echo.
echo ========================================
echo   Restart complete!
echo ========================================
echo.
echo Business services restarted (Manager keeps running)
echo.
