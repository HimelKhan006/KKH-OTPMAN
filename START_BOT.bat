@echo off
title OTPMAN 2 (KSI) Bot Runner
chcp 65001 >nul
color 0A
cd /d "%~dp0"

echo ===================================================
echo     OTPMAN 2 (KSI IPRN) TELEGRAM FORWARDER BOT
echo ===================================================
echo.
echo Terminating any duplicate bot instances...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo Starting bot in foreground mode...
echo (Press Ctrl+C to stop)
echo.

:LOOP
python bot.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] Bot stopped or crashed with exit code %ERRORLEVEL%.
    echo Restarting in 5 seconds...
    timeout /t 5 /nobreak >nul
    goto LOOP
)

pause
