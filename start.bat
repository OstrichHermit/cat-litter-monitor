@echo off
chcp 65001 >nul
title CatLitterMonitor

echo.
echo ========================================
echo   CatLitterMonitor - Starting...
echo ========================================
echo.

cd /d "%~dp0"

REM ===== go2rtc path config (modify if needed; add quotes manually if path has spaces) =====
set "GO2RTC_PATH=%~dp0..\go2rtc\go2rtc.exe"
set "GO2RTC_CONFIG=%~dp0..\go2rtc\go2rtc.yaml"
REM =========================================

REM Find Python executable
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable.replace('\\python.exe','\\pythonw.exe'))" 2^>nul') do set PYTHONW=%%i
if not defined PYTHONW set PYTHONW=pythonw.exe

if not exist "logs" mkdir logs

REM ===== duplicate-start guard: check port listeners =====
netstat -ano | findstr LISTENING | findstr /c:":1984 " >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] go2rtc is already running, port 1984 in use. Run stop.bat first.
    exit /b 1
)
netstat -ano | findstr LISTENING | findstr /c:":5002 " >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] main is already running, port 5002 in use. Run stop.bat first.
    exit /b 1
)
netstat -ano | findstr LISTENING | findstr /c:":5000 " >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] web is already running, port 5000 in use. Run stop.bat first.
    exit /b 1
)

echo [%time%] Starting go2rtc...
if not exist "%GO2RTC_PATH%" (
    echo [ERROR] go2rtc not found: %GO2RTC_PATH%
    echo         Please modify GO2RTC_PATH in this script.
    pause
    exit /b 1
)
if exist "%~dp0logs\go2rtc.log" move /y "%~dp0logs\go2rtc.log" "%~dp0logs\go2rtc.old.log" >nul
powershell -NoProfile -Command "Start-Process -FilePath '%GO2RTC_PATH%' -ArgumentList '-c','%GO2RTC_CONFIG%' -WindowStyle Hidden -RedirectStandardOutput '%~dp0logs\go2rtc.log' -RedirectStandardError '%~dp0logs\go2rtc_err.log'"
echo [OK] go2rtc started

echo Waiting for go2rtc...
ping -n 4 127.0.0.1 >nul

echo [%time%] Starting main...
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW%' -ArgumentList '%~dp0src\main.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
echo [OK] main started

ping -n 2 127.0.0.1 >nul

echo [%time%] Starting Web Server...
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW%' -ArgumentList '%~dp0src\web\app.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
echo [OK] Web Server started

echo [%time%] Starting manager...
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW%' -ArgumentList '%~dp0src\manager.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
echo [OK] manager started

ping -n 2 127.0.0.1 >nul

echo [%time%] Starting MCP Server...
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW%' -ArgumentList '%~dp0src\mcp\server.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"
echo [OK] MCP Server started

echo.
echo Waiting for services to initialize...
ping -n 9 127.0.0.1 >nul

REM ===== startup self-check =====
set FAILED=0
netstat -ano | findstr LISTENING | findstr /c:":1984 " >nul 2>&1
if errorlevel 1 (
    echo [FAIL] go2rtc port 1984 not listening
    set FAILED=1
) else (
    echo [OK] go2rtc listening on 1984
)
netstat -ano | findstr LISTENING | findstr /c:":5002 " >nul 2>&1
if errorlevel 1 (
    echo [WARN] main port 5002 not listening yet, may still be loading
    set FAILED=1
) else (
    echo [OK] main listening on 5002
)
netstat -ano | findstr LISTENING | findstr /c:":5000 " >nul 2>&1
if errorlevel 1 (
    echo [WARN] web port 5000 not listening yet
    set FAILED=1
) else (
    echo [OK] web listening on 5000
)
netstat -ano | findstr LISTENING | findstr /c:":5001 " >nul 2>&1
if errorlevel 1 (
    echo [WARN] mcp port 5001 not listening yet
    set FAILED=1
) else (
    echo [OK] mcp listening on 5001
)

echo.
echo ========================================
if "%FAILED%"=="1" (
    echo   Started with warnings - check logs\
) else (
    echo   All services started! ^(background^)
)
echo ========================================
echo Web: http://localhost:5000
echo Stop: run stop.bat
echo.
exit /b 0
