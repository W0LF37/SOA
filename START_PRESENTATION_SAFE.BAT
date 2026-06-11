@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "OPEN_TABS=0"

for %%A in (%*) do (
    if /I "%%~A"=="--open-tabs" set "OPEN_TABS=1"
)

set "CRITIPLAN_FORCE_FALLBACK=1"
set "CRITIPLAN_ENABLE_LLM_AUX=0"
set "OLLAMA_TIMEOUT_SECONDS=10"

echo.
echo  ====================================================
echo   CritiPlan ^| Presentation Safe Start
echo  ====================================================
echo.
echo  Mode        : Fast demo fallback
echo  Streamlit   : Disabled for faster startup
echo  Warm-up     : Dashboard + Monitor + Brief + AI Insights
echo.

call "%ROOT%START_FULL.BAT" --fast-demo --no-streamlit --no-browser --no-pause
if errorlevel 1 exit /b 1

python "%ROOT%scripts\prewarm_demo.py"
if errorlevel 1 (
    echo.
    echo  [WARN] Warm-up did not fully finish. Core app may still be usable.
)

if "%OPEN_TABS%"=="1" (
    start "" "http://127.0.0.1:5173/dashboard"
    start "" "http://127.0.0.1:5173/monitor"
    start "" "http://127.0.0.1:5173/brief"
)

echo.
echo  Ready for committee demo:
echo   Dashboard : http://127.0.0.1:5173/dashboard
echo   Monitor   : http://127.0.0.1:5173/monitor
echo   Brief     : http://127.0.0.1:5173/brief
echo.
exit /b 0
