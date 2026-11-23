@echo off
setlocal enabledelayedexpansion
title Enterprise Financial Consolidation Portal
cd /d "%~dp0"

echo ============================================================
echo    ENTERPRISE FINANCIAL CONSOLIDATION PORTAL (Ind AS 110)
echo    Built on LangGraph & Google Gemini | 100%% Formula Provenance
echo ============================================================
echo.

:: Detect Python executable (portable fallback chain)
set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0venv\Scripts\python.exe"
) else if exist "C:\Users\HP\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" (
    set "PY_EXE=C:\Users\HP\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
)

echo [OK] Python Engine: %PY_EXE%
echo [OK] Opening browser at: http://127.0.0.1:8000
echo.

:: Automatically open default browser after 2 seconds
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

:: Launch Web Portal
"%PY_EXE%" run_portal.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%.
    pause
)
