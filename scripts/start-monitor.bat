@echo off
setlocal
set "ROOT=%~dp0.."
call "%~dp0find-python.bat"
if errorlevel 1 exit /b 1
set "SHARE=%~1"
if "%SHARE%"=="" set "SHARE=%ROOT%\DreamRenderShare"
set "PYTHONPATH=%ROOT%\src"
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender monitor --share "%SHARE%" --host 127.0.0.1 --port 8766
