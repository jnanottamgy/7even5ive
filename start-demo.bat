@echo off
rem 7even5ive demo: double-click to start every server the phone needs, in this one window.
rem First run sets up Python packages (a few minutes, needs internet). Later runs start in seconds.
setlocal
cd /d "%~dp0core"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 or newer is needed: https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH" in the installer, then double-click this file again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating the Python environment...
  python -m venv .venv || goto fail
)

rem Install only when requirements.txt changed since the last successful install.
fc /b requirements.txt ".venv\requirements.installed" >nul 2>nul
if errorlevel 1 (
  echo Installing packages, a few minutes the first time...
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto fail
  copy /y requirements.txt ".venv\requirements.installed" >nul
)

if not exist data mkdir data
".venv\Scripts\python.exe" -m seventy5.serve_all
echo.
echo 7even5ive stopped.
pause
exit /b 0

:fail
echo.
echo Setup failed: scroll up for the error and send it to the team.
pause
exit /b 1
