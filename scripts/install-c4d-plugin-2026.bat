@echo off
setlocal
set "ROOT=%~dp0.."
set "SOURCE_SCRIPT=%ROOT%\cinema4d\DreamRenderSubmit.py"
set "SOURCE_PLUGIN=%ROOT%\cinema4d\plugin\DreamRender.pyp"
set "TARGET="

for /d %%D in ("%APPDATA%\Maxon\Maxon Cinema 4D 2026_*") do (
  set "TARGET=%%~fD\plugins\DreamRender"
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

if not exist "%SOURCE_SCRIPT%" (
  echo Missing submitter script: %SOURCE_SCRIPT%
  exit /b 1
)

if not exist "%SOURCE_PLUGIN%" (
  echo Missing plugin file: %SOURCE_PLUGIN%
  exit /b 1
)

if not exist "%TARGET%" (
  mkdir "%TARGET%"
)

copy /Y "%SOURCE_SCRIPT%" "%TARGET%\DreamRenderSubmit.py" >nul
copy /Y "%SOURCE_PLUGIN%" "%TARGET%\DreamRender.pyp" >nul
if errorlevel 1 (
  echo Could not install DreamRender plugin.
  exit /b 1
)

echo Installed DreamRender C4D plugin to:
echo %TARGET%
echo.
echo Restart Cinema 4D, then look for DreamRender Submit Render in the Extensions menu or Command Manager.
