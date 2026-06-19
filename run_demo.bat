@echo off
REM ============================================================================
REM CallTone — demo launcher (local stack + remote GPU via SSH tunnel)
REM ----------------------------------------------------------------------------
REM Prereqs (do these once, in order):
REM   1. On Vast:   bash model_server/setup_vast_instance.sh
REM                 → copy the MODEL_SERVER_TOKEN it prints.
REM   2. Put the token into .env.demo  (see .env.demo.example).
REM   3. Open an SSH tunnel in a SEPARATE terminal — keep it running.
REM      Remote model server listens on :8081 (Jupyter occupies :8080 on Vast):
REM      ssh -o ServerAliveInterval=30 -N -L 8090:localhost:8081 -p 44049 root@185.65.93.114
REM
REM Then run this script from the repo root:   run_demo.bat
REM ============================================================================

setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "ENV_FILE=%ROOT%.env.demo"

REM ---- load .env.demo (each line: KEY=value) ----
if not exist "%ENV_FILE%" (
    echo ERROR: %ENV_FILE% not found.
    echo Copy .env.demo.example to .env.demo and fill in MODEL_SERVER_TOKEN.
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if not "%%A"=="" (
        REM skip comment lines
        set "_line=%%A"
        if not "!_line:~0,1!"=="#" set "%%A=%%B"
    )
)

if "%MODEL_SERVER_TOKEN%"=="" (
    echo ERROR: MODEL_SERVER_TOKEN is empty in %ENV_FILE%.
    exit /b 1
)
if "%MODEL_SERVER_URL%"=="" set "MODEL_SERVER_URL=http://127.0.0.1:8090"

echo.
echo ============================================================================
echo   CallTone demo launcher
echo   MODEL_SERVER_URL    = %MODEL_SERVER_URL%
echo   MODEL_SERVER_TOKEN  = [set, %strlen:MODEL_SERVER_TOKEN% chars]
echo ============================================================================
echo.

REM ---- quick tunnel probe so we fail fast ----
echo [1/2] Probing SSH tunnel at %MODEL_SERVER_URL% ...
python -c "import httpx,sys; r=httpx.get('%MODEL_SERVER_URL%/v1/health', timeout=3); sys.exit(0 if r.status_code==200 else 1)" 2>nul
if errorlevel 1 (
    echo   ERROR: %MODEL_SERVER_URL%/v1/health did not respond.
    echo   Open the SSH tunnel in another terminal, then re-run:
    echo     ssh -o ServerAliveInterval=30 -N -L 8090:localhost:8081 -p 44049 root@185.65.93.114
    exit /b 1
)
echo   OK: model server reachable via tunnel

REM ---- delegate to run_local.bat (env vars inherited) ----
echo [2/2] Launching backend + frontend via run_local.bat ...
call "%ROOT%run_local.bat" %*

echo.
echo ============================================================================
echo   Once both windows say "ready":
echo     python scripts\demo_ready.py
echo   Then open http://localhost:8080 in your browser.
echo ============================================================================

endlocal
