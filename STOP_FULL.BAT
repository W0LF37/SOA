@echo off
setlocal EnableExtensions
set "QUIET=0"
for %%A in (%*) do (
    if /I "%%~A"=="--quiet" set "QUIET=1"
)

if "%QUIET%"=="0" (
    echo.
    echo  Stopping CritiPlan services...
)

call :kill_title "CritiPlan Full API*"
call :kill_title "CritiPlan Full UI*"
call :kill_title "CritiPlan Full Streamlit*"
call :kill_title "CritiPlan Full Ollama*"
call :kill_title "API"
call :kill_title "Frontend"
call :kill_title "Ollama"

call :kill_port 8000
call :kill_port 5173
call :kill_port 8501

if "%QUIET%"=="0" (
    echo  Done.
    pause
)
exit /b 0

:kill_title
taskkill /FI "WINDOWTITLE eq %~1" /T /F >NUL 2>&1
exit /b 0

:kill_port
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING" 2^>NUL') do (
    taskkill /PID %%P /T /F >NUL 2>&1
)
exit /b 0
