@echo off
setlocal
set "ROOT=%~dp0.."
call "%~dp0advanced\_INTERNAL_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
set "PYTHONPATH=%ROOT%\src"
echo Starting DreamRender App...
echo.
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender app
