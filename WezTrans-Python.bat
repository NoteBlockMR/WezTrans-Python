@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
    if not errorlevel 1 (
        py -3 app.py
        if errorlevel 1 pause
        exit /b
    )
)
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
    if not errorlevel 1 (
        python app.py
        if errorlevel 1 pause
        exit /b
    )
)
echo Python 3.10 or newer with tkinter was not found.
echo Install Python from https://www.python.org/downloads/ and enable the launcher or PATH.
pause
exit /b 1
