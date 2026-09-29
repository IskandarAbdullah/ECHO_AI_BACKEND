@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto python_failed
)

echo [2/3] Installing or checking backend packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed

echo [3/3] Starting ECHO AI Flask app at http://localhost:8000
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto server_failed
goto done

:python_failed
echo.
echo FAILED: Could not create the virtual environment using the Windows Python launcher (py -3).
echo Install Python 3.10-3.13 and enable the Python launcher, then retry.
py -0p
pause
exit /b 1

:pip_failed
echo.
echo FAILED: Dependency installation failed. Read the pip error above this message.
echo Check internet access, available disk space, and that Python is 3.10-3.13.
pause
exit /b 1

:server_failed
echo.
echo FAILED: The API process stopped. Read the error above; port 8000 may already be in use.
pause
exit /b 1

:done
endlocal
