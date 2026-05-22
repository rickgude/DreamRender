@echo off
setlocal
set "ROOT=%~dp0..\.."
call "%~dp0_INTERNAL_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
set "PYTHONPATH=%ROOT%\src"
echo Advanced classic DreamRender app.
echo.
echo Normal users should start START_DREAMRENDER.vbs from the project root.
echo This older Tkinter control panel is kept only for troubleshooting.
echo.
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender classic-app
