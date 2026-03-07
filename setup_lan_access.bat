@echo off
echo ========================================
echo 猫咪监控 - 局域网访问配置脚本
echo ========================================
echo.

echo 正在配置防火墙规则（需要管理员权限）...
echo.

netsh advfirewall firewall add rule name="CatLitterMonitor Web" dir=in action=allow protocol=TCP localport=5000

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✓ 防火墙规则配置成功！
    echo.
) else (
    echo.
    echo ✗ 配置失败！请右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo ========================================
echo 局域网访问信息
echo ========================================
echo.
echo 本机局域网IP地址：
ipconfig | findstr "IPv4"
echo.
echo 访问地址：
echo http://192.168.2.187:5000
echo.
echo 局域网内其他设备可以通过上述地址访问
echo ========================================
echo.

echo 按任意键启动猫咪监控系统...
pause > nul

cd /d "%~dp0"
python src/main.py
