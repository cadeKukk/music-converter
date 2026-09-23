@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python -X utf8 "%~dp0manage.py" enable-login
) else (
  py -3 -X utf8 "%~dp0manage.py" enable-login
)
echo.
pause
