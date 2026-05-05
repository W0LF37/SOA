@echo off
setlocal EnableExtensions

set "CRITIPLAN_FORCE_FALLBACK=1"
set "CRITIPLAN_ENABLE_LLM_AUX=0"
set "OLLAMA_TIMEOUT_SECONDS=10"

call "%~dp0START_FULL.BAT" --fast-demo %*
