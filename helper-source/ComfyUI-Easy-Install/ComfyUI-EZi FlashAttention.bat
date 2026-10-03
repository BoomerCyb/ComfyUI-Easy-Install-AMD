@echo off
cd /d "%~dp0"
set "PIP_CONSTRAINT=%~dp0amd\amd-constraints.txt"
set "UV_CONSTRAINT=%PIP_CONSTRAINT%"
.\python_embeded\python.exe .\Add-Ons\Tools\Helper-CEI\ComfyUI-EZi.py "Start ComfyUI FlashAttention.bat"
