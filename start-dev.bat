@echo off
setlocal enabledelayedexpansion

:: StockAIvo Development Environment Startup Script
echo Starting StockAIvo Development Environment...
echo.

:: Detect terminal type and set colors accordingly
:: Test if PowerShell is available for colored output
powershell -command "Write-Host 'Color Test' -ForegroundColor Green" >nul 2>&1
if %errorlevel% equ 0 (
    set "USE_POWERSHELL_COLORS=1"
    set "TERMINAL_TYPE=PS_COLORS"
) else (
    set "USE_POWERSHELL_COLORS=0"  
    set "TERMINAL_TYPE=NO_COLORS"
)

:: Color output function
:: Usage: call :ColorEcho "color" "message"
goto :skip_functions

:ColorEcho
if "%USE_POWERSHELL_COLORS%"=="1" (
    if "%~1"=="GREEN" powershell -command "Write-Host '%~2' -ForegroundColor Green"
    if "%~1"=="YELLOW" powershell -command "Write-Host '%~2' -ForegroundColor Yellow"
    if "%~1"=="RED" powershell -command "Write-Host '%~2' -ForegroundColor Red"
    if "%~1"=="BLUE" powershell -command "Write-Host '%~2' -ForegroundColor Blue"
) else (
    echo %~2
)
goto :eof

:skip_functions

:: Check Dependencies
call :ColorEcho "BLUE" "Checking dependencies..."
call :ColorEcho "BLUE" "Terminal Type: %TERMINAL_TYPE%"
echo.

:: Check pnpm
where pnpm >nul 2>nul
if %errorlevel% neq 0 (
    call :ColorEcho "RED" "Error: pnpm not found, please install pnpm first"
    echo Install command: npm install -g pnpm
    pause
    exit /b 1
)

:: Check uv
where uv >nul 2>nul
if %errorlevel% neq 0 (
    call :ColorEcho "RED" "Error: uv not found, please install uv first"
    echo Download: https://github.com/astral-sh/uv/releases
    pause
    exit /b 1
)

:: Check Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    call :ColorEcho "RED" "Error: Node.js not found, please install Node.js first"
    echo Download: https://nodejs.org/
    pause
    exit /b 1
)

:: Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    call :ColorEcho "RED" "Error: Python not found, please install Python 3.13+"
    echo Download: https://python.org/
    pause
    exit /b 1
)

:: Check Python Version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set python_version=%%i
call :ColorEcho "BLUE" "Python Version: !python_version!"

:: Create temp files to track processes
set "frontend_pid=%TEMP%\stockaivo_frontend.pid"
set "backend_pid=%TEMP%\stockaivo_backend.pid"

:: Clean old process files
if exist "%frontend_pid%" del "%frontend_pid%"
if exist "%backend_pid%" del "%backend_pid%"

call :ColorEcho "GREEN" "Dependencies check completed"
echo.

:: Start Frontend Service
call :ColorEcho "YELLOW" "Starting Frontend Service (React + Vite)"
cd frontend
if not exist node_modules (
    call :ColorEcho "BLUE" "Installing frontend dependencies"
    pnpm install
    if !errorlevel! neq 0 (
        call :ColorEcho "RED" "Frontend dependencies installation failed"
        cd ..
        pause
        exit /b 1
    )
)

:: Start frontend dev server
start "StockAIvo Frontend" cmd /c "pnpm dev && echo. && echo Frontend service stopped && pause"
cd ..

:: Wait for frontend service to start
call :ColorEcho "BLUE" "Waiting for frontend service to start"
timeout /t 3 /nobreak >nul

:: Start Backend Service
call :ColorEcho "YELLOW" "Starting Backend Service (FastAPI)"
if not exist .venv (
    call :ColorEcho "BLUE" "Creating virtual environment"
    uv venv
    if !errorlevel! neq 0 (
        call :ColorEcho "RED" "Virtual environment creation failed"
        pause
        exit /b 1
    )
)

:: Activate virtual environment and install dependencies
call :ColorEcho "BLUE" "Checking backend dependencies"
call .venv\Scripts\activate
uv sync --extra dev
if !errorlevel! neq 0 (
    call :ColorEcho "RED" "Backend dependencies installation failed"
    pause
    exit /b 1
)

:: Start backend dev server
start "StockAIvo Backend" cmd /c "uv run dev && echo. && echo Backend service stopped && pause"

echo.
call :ColorEcho "GREEN" "Development environment startup completed!"
echo.
call :ColorEcho "BLUE" "Service Information:"
echo   Frontend: http://localhost:3223
echo   Backend API: http://127.0.0.1:8000
echo   API Docs: http://127.0.0.1:8000/docs
echo.
call :ColorEcho "YELLOW" "Tips: Both services are running in separate windows, close windows to stop services"
echo.
call :ColorEcho "BLUE" "Press any key to open browser"
pause >nul

:: Open browser
start http://localhost:3223

call :ColorEcho "GREEN" "StockAIvo Development Environment is running!"
echo.
call :ColorEcho "BLUE" "Quick Commands:"
echo   - Stop all services: Close both command windows
echo   - Restart: Run this script again
echo   - View logs: Check corresponding command windows
echo.
pause