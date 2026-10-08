@echo off
cd /d "%~dp0..\"
title ComfyUI-Easy-Install-AMD - BoomerCyb WTiVo AMD Nodes
"python_embeded\python.exe" amd\install_wtivo_group.py boomercyb
if errorlevel 1 exit /b 1
if "%~1"=="" pause
