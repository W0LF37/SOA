@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "FRONTEND_DIR=%ROOT%frontend"
if defined TEMP (
    set "LOG_DIR=%TEMP%\CritiPlan\logs"
) else (
    set "LOG_DIR=%ROOT%run_logs"
)
if defined LOCALAPPDATA (
    set "RUNTIME_DIR=%LOCALAPPDATA%\CritiPlan\runtime"
) else (
    set "RUNTIME_DIR=%TEMP%\CritiPlan\runtime"
)
if not defined RUNTIME_DIR set "RUNTIME_DIR=%ROOT%run_logs\runtime"
set "CRITIPLAN_RUNTIME_DIR=%RUNTIME_DIR%"
set "API_HOST=127.0.0.1"
set "API_PORT=8000"
set "FRONTEND_HOST=127.0.0.1"
set "FRONTEND_PORT=5173"
set "STREAMLIT_HOST=127.0.0.1"
set "STREAMLIT_PORT=8501"
set "API_BASE=http://%API_HOST%:%API_PORT%/api"
set "API_HEALTH_URL=%API_BASE%/health"
set "REACT_UI_URL=http://%FRONTEND_HOST%:%FRONTEND_PORT%/login"
set "FRONTEND_CHECK_URL=http://%FRONTEND_HOST%:%FRONTEND_PORT%"
set "STREAMLIT_URL=http://%STREAMLIT_HOST%:%STREAMLIT_PORT%"
set "OLLAMA_URL=http://127.0.0.1:11434/api/tags"
set "NO_BROWSER=0"
set "NO_STREAMLIT=0"
set "NO_PAUSE=0"
set "SMOKE_TEST=0"
set "REUSE=0"
set "FAILED=0"
set "FAST_DEMO=0"
if not defined OLLAMA_TIMEOUT_SECONDS set "OLLAMA_TIMEOUT_SECONDS=30"
if not defined OLLAMA_NUM_CTX set "OLLAMA_NUM_CTX=2048"
if not defined OLLAMA_MIN_NUM_CTX set "OLLAMA_MIN_NUM_CTX=1024"
if not defined OLLAMA_MIN_NUM_PREDICT set "OLLAMA_MIN_NUM_PREDICT=512"
if not defined OLLAMA_MAX_NUM_PREDICT set "OLLAMA_MAX_NUM_PREDICT=2048"
if not defined CRITIPLAN_ENABLE_LLM_AUX set "CRITIPLAN_ENABLE_LLM_AUX=0"
if not defined CRITIPLAN_FORCE_FALLBACK set "CRITIPLAN_FORCE_FALLBACK=0"

call :prepare_runtime_dirs
if errorlevel 1 exit /b 1

if /I "%~1"=="--child-api" goto child_api
if /I "%~1"=="--child-ui" goto child_ui
if /I "%~1"=="--child-streamlit" goto child_streamlit
if /I "%~1"=="--child-ollama" goto child_ollama

title CritiPlan - Full Project Starter
color 0B
cls

for %%A in (%*) do (
    if /I "%%~A"=="--no-browser" set "NO_BROWSER=1"
    if /I "%%~A"=="--no-streamlit" set "NO_STREAMLIT=1"
    if /I "%%~A"=="--no-pause" set "NO_PAUSE=1"
    if /I "%%~A"=="--smoke-test" set "SMOKE_TEST=1"
    if /I "%%~A"=="--reuse" set "REUSE=1"
    if /I "%%~A"=="--fast-demo" set "FAST_DEMO=1"
    if /I "%%~A"=="--llm" set "CRITIPLAN_FORCE_FALLBACK=0"
)

if "%SMOKE_TEST%"=="1" (
    set "NO_BROWSER=1"
    set "NO_PAUSE=1"
)
if "%FAST_DEMO%"=="1" set "CRITIPLAN_FORCE_FALLBACK=1"

cd /d "%ROOT%"
2>NUL > "%LOG_DIR%\start_full_launcher.log" echo [%DATE% %TIME%] START_FULL launcher started.

echo.
echo  ====================================================
echo   CritiPlan ^| Full Project Starter
echo  ====================================================
echo.
echo  Project root : %ROOT%
echo  Runtime dir  : %RUNTIME_DIR%
echo  Log dir      : %LOG_DIR%
if "%CRITIPLAN_FORCE_FALLBACK%"=="1" echo  Planning    : fast demo fallback
if not "%CRITIPLAN_FORCE_FALLBACK%"=="1" echo  Planning    : local LLM with fallback
echo  API          : %API_HEALTH_URL%
echo  React UI     : %REACT_UI_URL%
if "%NO_STREAMLIT%"=="0" echo  Streamlit    : %STREAMLIT_URL%
echo.

if "%REUSE%"=="0" (
    echo [0/4] Cleaning old CritiPlan processes...
    call "%ROOT%STOP_FULL.BAT" --quiet
)

where python >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not available on PATH.
    set "FAILED=1"
    goto finish
)

where npm >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] npm is not available on PATH.
    set "FAILED=1"
    goto finish
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] frontend\package.json was not found.
    set "FAILED=1"
    goto finish
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies...
    pushd "%FRONTEND_DIR%"
    call npm install
    if errorlevel 1 (
        popd
        echo [ERROR] npm install failed.
        set "FAILED=1"
        goto finish
    )
    popd
)

echo [1/4] Checking Ollama...
where ollama >NUL 2>&1
if errorlevel 1 (
    echo       [WARN] Ollama not found. The app can still use fallback planning.
) else (
    call :check_url "%OLLAMA_URL%"
    if not errorlevel 1 (
        echo       Ollama already running.
    ) else (
        echo       Starting Ollama...
        start "CritiPlan Full Ollama" /D "%ROOT%" /MIN "%COMSPEC%" /c call "%~f0" --child-ollama
        call :wait_url "%OLLAMA_URL%" 24 "Ollama"
        if errorlevel 1 echo       [WARN] Ollama did not respond yet. Continuing.
    )
)

echo [2/4] Starting FastAPI backend...
start "CritiPlan Full API" /D "%ROOT%" /MIN "%COMSPEC%" /c call "%~f0" --child-api
call :wait_url "%API_HEALTH_URL%" 180 "API"
if errorlevel 1 (
    echo       [ERROR] API did not respond on %API_HEALTH_URL%.
    call :show_log_tail "%LOG_DIR%\api_stderr.log" "API stderr"
    set "FAILED=1"
    goto finish
)
echo       API ready.

echo [3/4] Starting React frontend...
start "CritiPlan Full UI" /D "%FRONTEND_DIR%" /MIN "%COMSPEC%" /c call "%~f0" --child-ui
call :wait_url "%FRONTEND_CHECK_URL%" 120 "Frontend"
if errorlevel 1 (
    echo       [ERROR] Frontend did not respond on %FRONTEND_CHECK_URL%.
    call :show_log_tail "%LOG_DIR%\frontend_stderr.log" "Frontend stderr"
    set "FAILED=1"
    goto finish
)
echo       Frontend ready.

echo [4/4] Starting Streamlit dashboard...
if "%NO_STREAMLIT%"=="1" (
    echo       Skipped by --no-streamlit.
) else (
    python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('streamlit') else 1)" >NUL 2>&1
    if errorlevel 1 (
        echo       [WARN] Streamlit is not installed. Continuing with React + API only.
    ) else (
        start "CritiPlan Full Streamlit" /D "%ROOT%" /MIN "%COMSPEC%" /c call "%~f0" --child-streamlit
        call :wait_url "%STREAMLIT_URL%" 120 "Streamlit"
        if errorlevel 1 (
            echo       [WARN] Streamlit did not respond yet. React UI is still ready.
        ) else (
            echo       Streamlit ready.
        )
    )
)

:finish
echo.
if "%FAILED%"=="1" (
    echo  Startup failed. Check logs in: %LOG_DIR%
    if "%SMOKE_TEST%"=="1" call "%ROOT%STOP_FULL.BAT" --quiet
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

echo  ====================================================
echo   Services are ready.
echo   React UI  : %REACT_UI_URL%
if "%NO_STREAMLIT%"=="0" echo   Streamlit : %STREAMLIT_URL%
echo   API Docs  : http://%API_HOST%:%API_PORT%/api/docs
echo   API Health: %API_HEALTH_URL%
echo  ====================================================
echo.

if "%SMOKE_TEST%"=="1" (
    echo  Smoke test passed. Stopping demo services...
    call "%ROOT%STOP_FULL.BAT" --quiet
    exit /b 0
)

if "%NO_BROWSER%"=="0" start "" "%REACT_UI_URL%"

if "%NO_PAUSE%"=="1" exit /b 0
echo  Press any key to close this launcher window. Services keep running.
pause >NUL
exit /b 0

:child_api
cd /d "%ROOT%"
python run_api.py 1>> "%LOG_DIR%\api_stdout.log" 2>> "%LOG_DIR%\api_stderr.log"
exit /b %ERRORLEVEL%

:child_ui
cd /d "%FRONTEND_DIR%"
set "CRITIPLAN_VITE_CACHE_DIR=%RUNTIME_DIR%\vite-ui-%FRONTEND_PORT%-%RANDOM%-%RANDOM%"
call npm run dev -- --host %FRONTEND_HOST% --port %FRONTEND_PORT% --strictPort 1>> "%LOG_DIR%\frontend_stdout.log" 2>> "%LOG_DIR%\frontend_stderr.log"
exit /b %ERRORLEVEL%

:child_streamlit
cd /d "%ROOT%"
python -m streamlit run src/ui/app.py --server.headless true --server.address %STREAMLIT_HOST% --server.port %STREAMLIT_PORT% 1>> "%LOG_DIR%\streamlit_stdout.log" 2>> "%LOG_DIR%\streamlit_stderr.log"
exit /b %ERRORLEVEL%

:child_ollama
cd /d "%ROOT%"
ollama serve 1>> "%LOG_DIR%\ollama_stdout.log" 2>> "%LOG_DIR%\ollama_stderr.log"
exit /b %ERRORLEVEL%

:prepare_runtime_dirs
call :ensure_writable_dir "%LOG_DIR%"
if errorlevel 1 (
    if defined LOCALAPPDATA (
        set "LOG_DIR=%LOCALAPPDATA%\CritiPlan\logs"
        call :ensure_writable_dir "%LOG_DIR%"
    )
)
if errorlevel 1 (
    echo [ERROR] Could not create a writable log directory.
    exit /b 1
)

call :ensure_writable_dir "%RUNTIME_DIR%"
if errorlevel 1 (
    set "RUNTIME_DIR=%LOG_DIR%\runtime"
    call :ensure_writable_dir "%RUNTIME_DIR%"
)
if errorlevel 1 (
    echo [ERROR] Could not create a writable runtime directory.
    exit /b 1
)
set "CRITIPLAN_RUNTIME_DIR=%RUNTIME_DIR%"
exit /b 0

:ensure_writable_dir
setlocal
set "_dir=%~1"
if not exist "%_dir%" mkdir "%_dir%" >NUL 2>&1
if not exist "%_dir%" (
    endlocal
    exit /b 1
)
2>NUL > "%_dir%\_critiplan_write_test.tmp" echo ok
if errorlevel 1 (
    endlocal
    exit /b 1
)
del /q "%_dir%\_critiplan_write_test.tmp" >NUL 2>&1
endlocal
exit /b 0

:check_url
python -c "import http.client, sys, urllib.parse; u=urllib.parse.urlparse(sys.argv[1]); port=u.port or 80; path=(u.path or '/') + (('?' + u.query) if u.query else ''); c=http.client.HTTPConnection(u.hostname, port, timeout=3); c.request('GET', path); r=c.getresponse(); r.read(64); c.close(); sys.exit(0 if 200 <= r.status < 500 else 1)" "%~1" >NUL 2>&1
exit /b

:wait_url
setlocal
set "_url=%~1"
set /a "_tries=%~2 / 3"
set "_name=%~3"
if %_tries% LSS 1 set "_tries=1"
:wait_loop
python -c "import http.client, sys, urllib.parse; u=urllib.parse.urlparse(sys.argv[1]); port=u.port or 80; path=(u.path or '/') + (('?' + u.query) if u.query else ''); c=http.client.HTTPConnection(u.hostname, port, timeout=3); c.request('GET', path); r=c.getresponse(); r.read(64); c.close(); sys.exit(0 if 200 <= r.status < 500 else 1)" "%_url%" >NUL 2>&1
if not errorlevel 1 ( endlocal & exit /b 0 )
echo       Waiting for %_name%...
ping -n 4 127.0.0.1 >NUL
set /a "_tries-=1"
if %_tries% GTR 0 goto wait_loop
endlocal
exit /b 1

:show_log_tail
echo.
echo  ---- %~2: last lines ----
if exist "%~1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%~1' -Tail 30" 2>NUL
) else (
    echo  Log file not found: %~1
)
echo  ---- end %~2 ----
echo.
exit /b 0
