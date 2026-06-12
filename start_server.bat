@echo off
REM ── Google Scholar Extractor — Start Server ──────────────────────
echo.
echo  ╔═══════════════════════════════════════════╗
echo  ║   Google Scholar Extractor — Starting...  ║
echo  ╚═══════════════════════════════════════════╝
echo.

cd /d "%~dp0backend"

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo  [INFO]  Starting Flask server on http://localhost:5000
echo  [INFO]  Press CTRL+C to stop.
echo.

python app.py

pause
