@echo off
cd /d "%~dp0..\"
title ComfyUI-Easy-Install-AMD - Pixaroma Workflows
"python_embeded\python.exe" amd\download_pixaroma.py
if errorlevel 1 exit /b 1
if "%~1"=="" pause
