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
echo Advanced worker-only mode.
echo.
echo Normal users should start START_DreamRender_App.vbs instead.
echo This window must stay open while this machine renders.
echo.
echo Share: %SHARE%
echo.
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender worker --share "%SHARE%" --c4d "C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe" --chunk-size 5
echo.
echo Worker stopped.
pause
