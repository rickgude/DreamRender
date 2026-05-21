@echo off
setlocal
set "ROOT=%~dp0.."
call "%~dp0_INTERNAL_find_python.bat"
if errorlevel 1 exit /b 1
set "PYTHONPATH=%ROOT%\src"
"%DREAMRENDER_PYTHON_EXE%" %DREAMRENDER_PYTHON_ARGS% -m dreamrender %*
