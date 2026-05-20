@echo off
setlocal
set "ROOT=%~dp0.."
set "SOURCE=%ROOT%\cinema4d\DreamRenderSubmit.py"
set "TARGET="

for /d %%D in ("%APPDATA%\Maxon\Maxon Cinema 4D 2026_*") do (
  set "TARGET=%%~fD\library\scripts"
  goto :found_target
)

:found_target
if "%TARGET%"=="" (
  echo Could not find a Cinema 4D 2026 preferences folder under:
  echo %APPDATA%\Maxon
  echo.
  echo Start Cinema 4D 2026 once, then run this installer again.
  exit /b 1
)

if not exist "%SOURCE%" (
  echo Missing submitter script: %SOURCE%
  exit /b 1
)

if not exist "%TARGET%" (
  mkdir "%TARGET%"
)

copy /Y "%SOURCE%" "%TARGET%\DreamRenderSubmit.py" >nul
if errorlevel 1 (
  echo Could not install DreamRenderSubmit.py
  exit /b 1
)

echo Installed DreamRender submitter to:
echo %TARGET%\DreamRenderSubmit.py
echo.
echo Restart Cinema 4D, then open Script Manager and run DreamRenderSubmit.
