@echo off
REM ============================================================================
REM CallTone — full local stack launcher (Windows)
REM ----------------------------------------------------------------------------
REM Brings up: backend (FastAPI :8000) + frontend (Vite :8080), seeds DB,
REM verifies all model weights are present, and opens the browser.
REM
REM Run from the repo root:    run_local.bat
REM Run with no checks:        run_local.bat --skip-checks
REM Run backend only:          run_local.bat --backend-only
REM Run frontend only:         run_local.bat --frontend-only
REM Stop everything:           run_local.bat --stop
REM ============================================================================

setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%calltone-UI"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=8080"
set "CONDA_ENV=calltone"

REM ---- arg parsing ----
set "MODE=full"
if /I "%~1"=="--backend-only" set "MODE=backend"
if /I "%~1"=="--frontend-only" set "MODE=frontend"
if /I "%~1"=="--skip-checks" set "MODE=full-nocheck"
if /I "%~1"=="--stop" goto :stop_all

echo.
echo ============================================================================
echo   CallTone local stack launcher
echo   Root:     %ROOT%
echo   Backend:  http://localhost:%BACKEND_PORT%
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo   Mode:     %MODE%
echo ============================================================================
echo.

if "%MODE%"=="full-nocheck" goto :start_services

REM ---- preflight: tool availability ----
echo [1/5] Checking required tools...
where python >nul 2>&1 || (echo   ERROR: python not found on PATH & exit /b 1)
where node   >nul 2>&1 || (echo   ERROR: node not found on PATH   & exit /b 1)
where npm    >nul 2>&1 || (echo   ERROR: npm not found on PATH    & exit /b 1)
echo   OK: python, node, npm available

REM ---- preflight: ports free ----
echo [2/5] Checking ports %BACKEND_PORT% and %FRONTEND_PORT% are free...
netstat -ano | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul && (
    echo   WARNING: port %BACKEND_PORT% is already in use.
    echo   Run:  run_local.bat --stop   to free it, or kill the process manually.
    exit /b 1
)
netstat -ano | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul && (
    echo   WARNING: port %FRONTEND_PORT% is already in use.
    echo   Run:  run_local.bat --stop   to free it, or kill the process manually.
    exit /b 1
)
echo   OK: both ports free

REM ---- preflight: model weights ----
echo [3/5] Checking model weights...
set "MODELS_OK=1"
if not exist "%ROOT%models\skill_implementation\models\Meta-Llama-3.1-8B-Instruct-Q8_0.gguf" (
    echo   MISSING: Llama 3.1 8B GGUF ^(skill_implementation\models\^)
    set "MODELS_OK=0"
)
if not exist "%ROOT%models\LAYER_1\models\sensevoice" (
    echo   MISSING: SenseVoice  ^(LAYER_1\models\sensevoice\^)
    set "MODELS_OK=0"
)
if not exist "%ROOT%models\LAYER_1\models\pyannote" (
    echo   MISSING: pyannote    ^(LAYER_1\models\pyannote\^)
    set "MODELS_OK=0"
)
if not exist "%ROOT%models\LAYER_1\resemble-enhance" (
    echo   MISSING: resemble-enhance ^(LAYER_1\resemble-enhance\^)
    set "MODELS_OK=0"
)
if "!MODELS_OK!"=="0" (
    echo.
    echo   To download models run:   python download_models.py
    echo   Pipeline calls will fail until weights are present, but the
    echo   backend API and frontend will still start. Continue? [y/N]
    set /p "ANSWER="
    if /I not "!ANSWER!"=="y" exit /b 1
) else (
    echo   OK: all model weights present
)

REM ---- preflight: backend deps + DB seed ----
echo [4/5] Verifying backend deps and database...
pushd "%BACKEND_DIR%"
python -c "import fastapi, sqlalchemy, jose, passlib" 2>nul || (
    echo   Backend deps missing; installing from requirements.txt...
    python -m pip install -r requirements.txt || (popd & exit /b 1)
)
if not exist "calltone.db" (
    echo   Seeding fresh SQLite database...
    python -m app.seed_data || (popd & exit /b 1)
) else (
    echo   OK: calltone.db present
)
popd

REM ---- preflight: frontend deps ----
echo [5/5] Verifying frontend deps...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo   node_modules missing; running npm install...
    pushd "%FRONTEND_DIR%"
    call npm install || (popd & exit /b 1)
    popd
) else (
    echo   OK: node_modules present
)

:start_services
echo.
echo ============================================================================
echo   Starting services...
echo ============================================================================

if "%MODE%"=="frontend" goto :start_frontend

REM ---- start backend in its own window ----
echo Launching backend  ^(uvicorn @ :%BACKEND_PORT%^)
start "CallTone Backend" cmd /k "cd /d %BACKEND_DIR% && python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload"

REM ---- wait for backend health ----
echo Waiting for backend to come up...
set "WAITED=0"
:wait_backend
timeout /t 2 /nobreak >nul
set /a "WAITED+=2"
curl -s -o nul -w "%%{http_code}" http://localhost:%BACKEND_PORT%/api/health 2>nul | findstr "200" >nul
if %ERRORLEVEL%==0 (
    echo   OK: backend responding on /api/health after !WAITED!s
    goto :backend_ready
)
if !WAITED! geq 60 (
    echo   ERROR: backend did not respond within 60s. Check the backend window.
    exit /b 1
)
goto :wait_backend

:backend_ready
if "%MODE%"=="backend" goto :done

:start_frontend
echo Launching frontend ^(vite @ :%FRONTEND_PORT%^)
start "CallTone Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm run dev"

REM ---- wait for frontend ----
echo Waiting for frontend...
set "WAITED=0"
:wait_frontend
timeout /t 2 /nobreak >nul
set /a "WAITED+=2"
curl -s -o nul -w "%%{http_code}" http://localhost:%FRONTEND_PORT% 2>nul | findstr /R "200 304" >nul
if %ERRORLEVEL%==0 (
    echo   OK: frontend responding on :%FRONTEND_PORT% after !WAITED!s
    goto :frontend_ready
)
if !WAITED! geq 90 (
    echo   WARNING: frontend slow to come up. Check the frontend window.
    goto :done
)
goto :wait_frontend

:frontend_ready
echo.
echo ============================================================================
echo   ALL SERVICES UP
echo ----------------------------------------------------------------------------
echo   Backend  API   : http://localhost:%BACKEND_PORT%/api/health/detailed
echo   Backend  docs  : http://localhost:%BACKEND_PORT%/docs
echo   Frontend       : http://localhost:%FRONTEND_PORT%
echo.
echo   Seeded accounts ^(password: Password123!^):
echo     admin@calltone.ai   ^(super_admin^)
echo     qa@calltone.ai      ^(qa^)
echo     agent1@calltone.ai  ^(agent^)
echo.
echo   Stop everything:  run_local.bat --stop
echo ============================================================================
echo.
start "" "http://localhost:%FRONTEND_PORT%"

:done
endlocal
exit /b 0

REM ============================================================================
:stop_all
echo Stopping CallTone services on ports %BACKEND_PORT% and %FRONTEND_PORT%...
for %%P in (%BACKEND_PORT% %FRONTEND_PORT%) do (
    for /f "tokens=5" %%X in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        echo   Killing PID %%X on port %%P
        taskkill /F /PID %%X >nul 2>&1
    )
)
echo Done.
endlocal
exit /b 0
