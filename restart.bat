@echo off
chcp 65001 >nul
title CatLitterMonitor - Restart

echo.
echo ========================================
echo   CatLitterMonitor - Restarting...
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

REM Find Python executable (full python for scripts)
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set PYTHON=%%i
if not defined PYTHON set PYTHON=python

echo [%time%] Stopping business processes...

REM Kill all cat-litter-monitor processes except manager and web
"%PYTHON%" "%~dp0scripts\kill_monitor.py" manager web >nul 2>&1

REM Kill go2rtc
taskkill /F /IM go2rtc.exe >nul 2>&1

echo       Business processes stopped (Manager keeps running)

echo.
echo Waiting for processes to exit...
ping -n 4 127.0.0.1 >nul

REM ===== duplicate-start guard: confirm ports released =====
netstat -ano | findstr LISTENING | findstr /c:":1984 " >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] go2rtc port 1984 still in use, restart aborted. Run stop.bat first.
    exit /b 1
)
netstat -ano | findstr LISTENING | findstr /c:":5002 " >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] main port 5002 still in use, restart aborted. Run stop.bat first.
    exit /b 1
)

echo.
echo [%time%] Starting business services...

echo [1/2] Starting go2rtc...
if not exist "%GO2RTC_PATH%" (
    echo [ERROR] go2rtc not found: %GO2RTC_PATH%
    echo         Please modify GO2RTC_PATH in this script.
    exit /b 1
)
if exist "%~dp0logs\go2rtc.log" move /y "%~dp0logs\go2rtc.log" "%~dp0logs\go2rtc.old.log" >nul
powershell -NoProfile -Command "Start-Process -FilePath '%GO2RTC_PATH%' -ArgumentList '-c','%GO2RTC_CONFIG%' -WindowStyle Hidden -RedirectStandardOutput '%~dp0logs\go2rtc.log' -RedirectStandardError '%~dp0logs\go2rtc_err.log'"
ping -n 4 127.0.0.1 >nul

echo [2/2] Starting Main...
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW%' -ArgumentList '%~dp0src\main.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden"

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

echo.
echo ========================================
if "%FAILED%"=="1" (
    echo   Restart finished with warnings - check logs\
) else (
    echo   Restart complete! ^(Manager and web keep running^)
)
echo ========================================
echo.
exit /b 0
