@echo off
rem Double-click to start the local development environment (see tools\dev\start-dev.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\dev\start-dev.ps1"
if errorlevel 1 (
    echo.
    echo Startup failed, see the messages above.
)
pause
