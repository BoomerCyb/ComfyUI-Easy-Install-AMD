@echo off
setlocal
title ComfyUI-Easy-Install-AMD - Toggle Bitsandbytes
cd /d "%~dp0..\..\"
"python_embeded\python.exe" amd\bitsandbytes_toggle.py
if errorlevel 1 exit /b 1
if "%~1"=="" pause
