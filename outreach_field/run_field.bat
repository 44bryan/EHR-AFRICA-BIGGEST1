@echo off
chcp 65001 >nul
title EHR Africa - Outreach Field App
color 0A
echo.
echo  ================================================
echo   EHR Africa - Outreach Field Application
echo   Running on: http://localhost:8765
echo   Open your browser to: http://localhost:8765
echo  ================================================
echo.

cd /d "%~dp0.."

:: Check Python — try python, then py launcher, then common install paths
set PYTHON_CMD=
python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
    goto python_found
)

py --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py
    goto python_found
)

:: Try common install paths
if exist "C:\Python313\python.exe" ( set PYTHON_CMD=C:\Python313\python.exe & goto python_found )
if exist "C:\Python312\python.exe" ( set PYTHON_CMD=C:\Python312\python.exe & goto python_found )
if exist "C:\Python311\python.exe" ( set PYTHON_CMD=C:\Python311\python.exe & goto python_found )
if exist "C:\Python310\python.exe" ( set PYTHON_CMD=C:\Python310\python.exe & goto python_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" ( set PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe & goto python_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" ( set PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe & goto python_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" ( set PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe & goto python_found )
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" ( set PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python310\python.exe & goto python_found )

echo ERROR: Python not found. Please install Python 3.10 or newer from https://python.org
echo        Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:python_found
echo Python found: %PYTHON_CMD%

:: Install dependencies if needed
if not exist venv\ (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv venv
)
call venv\Scripts\activate.bat

:: Install minimal requirements
pip install django pillow --quiet

:: Run migrations on first run
echo Running database setup...
python manage.py migrate --settings=outreach_field.settings_field --run-syncdb 2>nul

:: Create default admin if needed
python outreach_field\create_admin.py 2>nul

echo.
echo  Opening browser...
start http://localhost:8765

:: Start server
python manage.py runserver 8765 --settings=outreach_field.settings_field --noreload

pause
