@echo off
cd /d "%~dp0..\"
title ComfyUI-Easy-Install-AMD - MostAadTech WTiVo Nodes
"python_embeded\python.exe" amd\install_wtivo_group.py mostaadtech
if errorlevel 1 goto failed
if "%~1"=="" pause
exit /b 0
:failed
rem Keep the window open on errors too, unless a caller passed an argument (EZi uses NoPause).
if "%~1"=="" pause
exit /b 1
