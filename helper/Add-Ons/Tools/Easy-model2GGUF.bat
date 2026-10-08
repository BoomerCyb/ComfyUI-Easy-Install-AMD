@echo off
cd /d "%~dp0..\..\"
"python_embeded\python.exe" amd\windows_tools.py gguf
if errorlevel 1 exit /b 1
if "%~1"=="" pause
