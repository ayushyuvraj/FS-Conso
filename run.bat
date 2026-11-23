@echo off
setlocal
title Enterprise Financial Consolidation Portal
cd /d "%~dp0"

echo ============================================================
echo    ENTERPRISE FINANCIAL CONSOLIDATION PORTAL (Ind AS 110)
echo    Built on LangGraph and Google Gemini - 100%% Formulas
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
echo [OK] Launching Portal: http://127.0.0.1:8000
echo.

:: Launch browser in background after 2 seconds via PowerShell
start "" powershell -windowstyle hidden -command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"

:: Launch Web Server
"%PY_EXE%" run_portal.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with code %ERRORLEVEL%.
    pause
)
