@echo off
REM Double-clickable installer for Windows. Finds Python, then hands over
REM to install.py which does the real work.

setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 install.py %*
    goto done
)

where python >nul 2>&1
if %errorlevel%==0 (
    python install.py %*
    goto done
)

echo Python was not found on this computer.
echo Install Python 3.8 or newer from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup, then run this again.

:done
echo.
pause
