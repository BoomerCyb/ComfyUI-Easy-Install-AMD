@echo off
cd /d "%~dp0..\"
title ComfyUI-Easy-Install-AMD - Pixaroma Workflows
rem Downloads every Pixaroma episode's workflows; files already in workflows\Pixaroma are skipped.
"python_embeded\python.exe" amd\download_pixaroma.py
pause
