@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=%~dp0runtime\python\python.exe"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist "%PYTHON%" (
    echo [ERROR] Embedded Python runtime is missing or incomplete.
    echo Please extract the complete release package and try again.
    pause
    exit /b 1
)

if /i "%~1"=="--check" goto check_installation

if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

if "%COMFYUI_URL%"=="" set "COMFYUI_URL=http://127.0.0.1:8189"
if "%MEDIA_GATEWAY_HOST%"=="" set "MEDIA_GATEWAY_HOST=0.0.0.0"
if "%MEDIA_GATEWAY_PORT%"=="" set "MEDIA_GATEWAY_PORT=8765"
echo VideoFree is starting...
echo ComfyUI: %COMFYUI_URL%
echo Web UI:   http://127.0.0.1:%MEDIA_GATEWAY_PORT%
if not "%MEDIA_GATEWAY_HOST%"=="127.0.0.1" echo LAN API:  http://%COMPUTERNAME%:%MEDIA_GATEWAY_PORT%
echo Press Ctrl+C to stop.
echo.

"%PYTHON%" -B -s -m backend.launcher

if errorlevel 1 (
    echo.
    echo [ERROR] VideoFree stopped unexpectedly.
    pause
)

endlocal
exit /b

:check_installation
"%PYTHON%" -B -s -c "from backend.main import app; from backend.bootstrap import check_installation; check_installation(); print('Runtime check OK:', app.title, app.version)"
exit /b %errorlevel%
