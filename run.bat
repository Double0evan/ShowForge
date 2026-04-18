@echo off
cd /d %~dp0

if not exist ".venv\Scripts\python.exe" (
    echo [V3 Bot] Virtual environment not found. Setting up...
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create venv.
        echo Make sure Python 3.11+ is installed and on your PATH.
        echo Download from: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo [V3 Bot] Installing dependencies...
    .venv\Scripts\pip.exe install --upgrade pip
    .venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: pip install failed.
        echo Check the error above. Common fix: install Visual C++ Build Tools
        echo or upgrade pip and try again.
        pause
        exit /b 1
    )
    echo.
    echo [V3 Bot] Setup complete!
    echo.
)

.venv\Scripts\python.exe run.py
pause
