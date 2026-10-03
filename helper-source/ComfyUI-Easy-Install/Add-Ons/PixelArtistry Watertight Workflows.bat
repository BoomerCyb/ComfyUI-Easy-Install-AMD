@echo off
cd /d "%~dp0..\"
title ComfyUI-Easy-Install-AMD - PixelArtistry Watertight Workflows
"python_embeded\python.exe" amd\download_pixelartistry.py
if errorlevel 1 exit /b 1
if "%~1"=="" pause
