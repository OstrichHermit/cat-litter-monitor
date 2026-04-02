@echo off
chcp 65001 >nul
title CatLitterMonitor - Restart

echo.
echo ========================================
echo   CatLitterMonitor - Restarting...
echo ========================================
echo.

cd /d "%~dp0"

:: ===== go2rtc 路径配置（可按需修改）=====
:: 默认值：go2rtc 位于项目同级目录下
set "GO2RTC_PATH=%~dp0..\go2rtc\go2rtc.exe"
set "GO2RTC_CONFIG=%~dp0..\go2rtc\go2rtc.yaml"
:: =========================================

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
if not exist "%GO2RTC_PATH%" (
    echo [ERROR] go2rtc not found: %GO2RTC_PATH%
    echo         Please modify GO2RTC_PATH in this script or copy go2rtc to the correct location.
)
powershell -Command "Start-Process cmd.exe -ArgumentList '/c %GO2RTC_PATH% -c %GO2RTC_CONFIG% >> %CD%\logs\go2rtc.log 2>&1' -WindowStyle Hidden"

timeout /t 3 /nobreak >nul

echo [2/3] Starting Main...
start "CatLitterMonitor-Main" /B pythonw "%~dp0src\main.py"

timeout /t 2 /nobreak >nul

echo [3/3] Starting MCP Server...
start "CatLitterMonitor-MCP" /B pythonw "%~dp0src\mcp\server.py"

echo.
echo ========================================
echo   Restart complete!
echo ========================================
echo.
echo Business services restarted (Manager keeps running)
echo.
