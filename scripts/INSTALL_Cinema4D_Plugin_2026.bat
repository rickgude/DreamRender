@echo off
setlocal
set "ROOT=%~dp0.."
set "SOURCE_SCRIPT=%ROOT%\cinema4d\DreamRenderSubmit.py"
set "SOURCE_PLUGIN=%ROOT%\cinema4d\plugin\DreamRender.pyp"
set "TARGET="
set "PREFS="

echo DreamRender Cinema 4D 2026 plugin installer
echo.

for /d %%D in ("%APPDATA%\Maxon\Maxon Cinema 4D 2026_*") do (
  set "PREFS=%%~fD"
  set "TARGET=%%~fD\plugins\DreamRender"
  goto :found_target
)

:found_target
if "%TARGET%"=="" (
  echo Could not find a Cinema 4D 2026 preferences folder under:
  echo %APPDATA%\Maxon
  echo.
  echo Start Cinema 4D 2026 once, close it, then run this installer again.
  pause
  exit /b 1
)

if not exist "%SOURCE_SCRIPT%" (
  echo Missing submitter script: %SOURCE_SCRIPT%
  pause
  exit /b 1
)

if not exist "%SOURCE_PLUGIN%" (
  echo Missing plugin file: %SOURCE_PLUGIN%
  pause
  exit /b 1
)

if not exist "%TARGET%" (
  mkdir "%TARGET%"
)

copy /Y "%SOURCE_SCRIPT%" "%TARGET%\DreamRenderSubmit.py" >nul
copy /Y "%SOURCE_PLUGIN%" "%TARGET%\DreamRender.pyp" >nul
if errorlevel 1 (
  echo Could not install DreamRender plugin.
  pause
  exit /b 1
)

if exist "%PREFS%\library\scripts\DreamRenderSubmit.py" (
  del /Q "%PREFS%\library\scripts\DreamRenderSubmit.py" >nul 2>nul
)

echo Installed DreamRender C4D plugin to:
echo %TARGET%
echo.
echo Restart Cinema 4D, then use:
echo Extensions ^> DreamRender Submit Render
echo.
pause
