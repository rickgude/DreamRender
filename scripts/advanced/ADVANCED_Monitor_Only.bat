@echo off
setlocal
set "ROOT=%~dp0..\.."
call "%~dp0_INTERNAL_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
set "SHARE=%~1"
if "%SHARE%"=="" set "SHARE=%ROOT%\DreamRenderShare"
set "PYTHONPATH=%ROOT%\src"
echo Advanced monitor-only mode.
echo.
echo Normal users should start START_DREAMRENDER.vbs from the project root.
echo Dashboard: http://127.0.0.1:8766
echo Share: %SHARE%
echo.
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender monitor --share "%SHARE%" --host 127.0.0.1 --port 8766
echo.
echo Monitor stopped.
pause
