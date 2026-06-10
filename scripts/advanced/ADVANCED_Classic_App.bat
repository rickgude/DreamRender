@echo off
setlocal
set "ROOT=%~dp0..\.."

call "%~dp0_INTERNAL_find_python.bat"
if errorlevel 1 exit /b 1
set "PYTHONPATH=%ROOT%\src"

echo The classic DreamRender app has been retired.
echo Launching the current DreamRender App instead.
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender app-v2
