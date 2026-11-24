@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=python"
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3.12"
)

echo ============================================================
echo   Agentic Workplace - FastAPI Backend ^& Vite Frontend
echo ============================================================

if not exist "%~dp0Target-MAS-Dataset-main\frontend\node_modules\.bin\vite.cmd" (
    echo [Setup] Installing frontend dependencies...
    pushd "%~dp0Target-MAS-Dataset-main\frontend"
    call npm install
    if errorlevel 1 (
        popd
        echo [Error] npm install failed.
        pause
        exit /b 1
    )
    popd
)

echo [1/2] Starting FastAPI Backend on http://127.0.0.1:8000 ...
start "Agentic Workplace - FastAPI Backend (8000)" cmd /k "cd /d ""%~dp0Target-MAS-Dataset-main"" && set PYTHONPATH=. && %PYTHON_CMD% -m uvicorn api.main:app --host 127.0.0.1 --port 8000"

echo [2/2] Starting Vite Frontend on http://127.0.0.1:5173/ ...
start "Agentic Workplace - Vite Frontend (5173)" cmd /k "cd /d ""%~dp0Target-MAS-Dataset-main\frontend"" && npm run dev -- --host 127.0.0.1 --port 5173"

echo.
echo   Backend API : http://127.0.0.1:8000
echo   Frontend UI : http://127.0.0.1:5173/
echo.
echo Both servers launched in separate windows. Close those windows to stop them.
pause
