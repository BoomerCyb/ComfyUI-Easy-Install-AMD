@echo off
cd /d "%~dp0..\"
".\python_embeded\python.exe" amd\maintenance.py insightface
if errorlevel 1 exit /b 1
if "%~1"=="" pause
