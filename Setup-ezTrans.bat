@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-python32.ps1"
if errorlevel 1 (
    echo 32-bit Python setup failed.
    pause
    exit /b 1
)
echo Setup complete. You may now use ezTrans.
pause
