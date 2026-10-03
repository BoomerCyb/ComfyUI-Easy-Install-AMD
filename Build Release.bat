@echo off
cd /d "%~dp0"
py -3 tools\package_installer.py
if errorlevel 1 exit /b 1
pause
