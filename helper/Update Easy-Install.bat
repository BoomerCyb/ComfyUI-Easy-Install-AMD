@echo off
setlocal
set "RC=1"
title ComfyUI-Easy-Install-AMD - Update Easy Install
cd /d "%~dp0"
set "NOPAUSE=%~1"
if not exist "python_embeded\python.exe" (
    echo Run this from a ComfyUI-Easy-Install-AMD installation folder.
    goto done
)
echo Updates the Easy Install launchers and tools from the latest AMD release.
echo ComfyUI, models, custom nodes and Python packages are not changed.
echo.
"python_embeded\python.exe" "amd\self_update.py"
set "RC=%errorlevel%"
if not "%RC%"=="0" echo Easy Install update did not complete.
:done
if "%NOPAUSE%"=="" pause
rem cmd.exe reads a parenthesized block whole, so replacing this file inside it is safe.
(if exist "%~f0.new" move /y "%~f0.new" "%~f0" >nul) & exit /b %RC%
