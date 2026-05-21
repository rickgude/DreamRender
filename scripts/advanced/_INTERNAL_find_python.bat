@echo off

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
  set "DREAMRENDER_PYTHON_EXE=%~dp0..\..\.venv\Scripts\python.exe"
  set "DREAMRENDER_PYTHON_ARGS="
  exit /b 0
)

if exist "C:\Python314\python.exe" (
  set "DREAMRENDER_PYTHON_EXE=C:\Python314\python.exe"
  set "DREAMRENDER_PYTHON_ARGS="
  exit /b 0
)

for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if exist "%%~fP\python.exe" (
    set "DREAMRENDER_PYTHON_EXE=%%~fP\python.exe"
    set "DREAMRENDER_PYTHON_ARGS="
    exit /b 0
  )
)

where py.exe >nul 2>nul
if not errorlevel 1 (
  set "DREAMRENDER_PYTHON_EXE=py.exe"
  set "DREAMRENDER_PYTHON_ARGS=-3"
  exit /b 0
)

where python.exe >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%P in ('where python.exe') do (
    echo %%P | findstr /i "\\Microsoft\\WindowsApps\\python.exe" >nul
    if errorlevel 1 (
      set "DREAMRENDER_PYTHON_EXE=%%P"
      set "DREAMRENDER_PYTHON_ARGS="
      exit /b 0
    )
  )
)

echo Could not find regular Python. Install Python 3.10+ from python.org.
echo Do not use Cinema 4D c4dpy.exe for DreamRender workers.
exit /b 1
