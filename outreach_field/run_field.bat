@echo off
title EHR Africa — Outreach Field App
color 0A
echo.
echo  ================================================
echo   EHR Africa — Outreach Field Application
echo   Running on: http://localhost:8765
echo   Open your browser to: http://localhost:8765
echo  ================================================
echo.

cd /d "%~dp0.."

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10 or newer.
    pause
    exit /b 1
)

:: Install dependencies if needed
if not exist venv\ (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Install minimal requirements
pip install django pillow --quiet

:: Run migrations on first run
echo Running database setup...
python manage.py migrate --settings=outreach_field.settings_field --run-syncdb 2>nul

:: Create default admin if needed
python manage.py shell --settings=outreach_field.settings_field -c "
from apps.accounts.models import User
if not User.objects.filter(username='field_admin').exists():
    u = User.objects.create_superuser('field_admin', '', 'field123')
    u.role = 'super_admin'
    u.save()
    print('Default login: field_admin / field123')
" 2>nul

echo.
echo  Opening browser...
start http://localhost:8765

:: Start server
python manage.py runserver 8765 --settings=outreach_field.settings_field --noreload

pause
