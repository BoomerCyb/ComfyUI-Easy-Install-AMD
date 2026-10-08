@echo off
setlocal
title ComfyUI-Easy-Install-AMD - Toggle Bitsandbytes
cd /d "%~dp0..\..\"
"python_embeded\python.exe" amd\bitsandbytes_toggle.py
if errorlevel 1 goto failed
if "%~1"=="" pause
exit /b 0
:failed
rem Keep the window open on errors too, unless a caller passed an argument (EZi uses NoPause).
if "%~1"=="" pause
exit /b 1
