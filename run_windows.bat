@echo off
rem ===============================================================================================================
rem  MTSU Task Validation - starts the dashboard on Windows. Just double-click this file.
rem
rem  First run:  finds Python 3.10-3.14 (installs Python 3.12 with winget if there is none), creates venv\,
rem              installs requirements.txt, and creates .env from .env.example (Notepad opens: fill it in, save, close).
rem  Next runs:  starts straight away. Packages are installed again only when requirements.txt changes.
rem
rem  Stop: close this window (or press Ctrl+C).      Option:  run_windows.bat --no-open   (don't open the browser)
rem ===============================================================================================================
setlocal EnableExtensions
cd /d "%~dp0"
title MTSU Task Validation
set "PYTHONIOENCODING=utf-8"
set "VENV=%~dp0venv"
set "VPY=%~dp0venv\Scripts\python.exe"
set "STAMP=%~dp0venv\requirements.installed"
set "OPEN=--open"
if /i "%~1"=="--no-open" set "OPEN="

rem ---- 1. Settings (.env): LLM address, key and model ------------------------------------------------------------
if exist ".env" goto env_ok
copy /y ".env.example" ".env" >nul
echo.
echo  Created .env from .env.example. Fill in the LLM settings, then save and close Notepad.
echo.
if defined OPEN start "" /wait notepad ".env"
:env_ok

rem ---- 2. Python environment (venv\). One copied from another PC does not work, so it is made again. -----------
if not exist "%VPY%" goto make_venv
"%VPY%" -c "import sys" >nul 2>&1 && goto venv_ok
echo The venv folder does not work on this PC. Making a new one...
rmdir /s /q "%VENV%"
:make_venv
call :find_python
if not defined PY goto no_python
echo Creating the Python environment in venv\ with %PY%
"%PY%" -m venv "%VENV%" || goto failed
:venv_ok

rem ---- 3. Packages: installed only when requirements.txt changed since the last successful install ------------
fc /b "requirements.txt" "%STAMP%" >nul 2>&1 && goto run
echo Installing Python packages. The first time this takes a few minutes...
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%VPY%" -m pip install --disable-pip-version-check --retries 10 --timeout 60 -r requirements.txt || goto pip_failed
copy /y "requirements.txt" "%STAMP%" >nul

rem ---- 4. Run. If the dashboard is already running, this only opens it in the browser. ------------------------
:run
"%VPY%" dashboard\app.py %OPEN%
if errorlevel 1 goto failed
exit /b 0

rem ---------------------------------------------------------------------------------------------------------------
:find_python
set "PY="
for %%V in (3.12 3.13 3.11 3.10 3.14) do if not defined PY (
  for /f "delims=" %%P in ('py -%%V -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
)
if defined PY exit /b 0
for /f "delims=" %%P in ('python -c "import sys; v = sys.version_info; print(sys.executable if v.major == 3 and v.minor in range(10, 15) else '')" 2^>nul') do set "PY=%%P"
if defined PY exit /b 0
where winget >nul 2>&1 || exit /b 0
echo Python 3.10-3.14 was not found. Installing Python 3.12 with winget...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
exit /b 0

:no_python
echo.
echo  Could not find or install Python. Install Python 3.12 from https://www.python.org/downloads/
echo  (tick "Add python.exe to PATH"), then run this file again.
goto stop

:pip_failed
echo.
echo  Installing the packages failed (see the messages above). Check the internet connection and run this again.
goto stop

:failed
echo.
echo  The dashboard stopped with an error (see the messages above).

:stop
echo.
pause
exit /b 1
