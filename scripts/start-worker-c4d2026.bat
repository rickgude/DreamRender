@echo off
setlocal
set "ROOT=%~dp0.."
call "%~dp0find-python.bat"
if errorlevel 1 exit /b 1
set "SHARE=%~1"
if "%SHARE%"=="" set "SHARE=%ROOT%\DreamRenderShare"
set "PYTHONPATH=%ROOT%\src"
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender worker --share "%SHARE%" --c4d "C:\Program Files\Maxon Cinema 4D 2026\Commandline.exe" --chunk-size 5
