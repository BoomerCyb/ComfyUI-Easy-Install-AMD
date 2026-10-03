@echo off
cd /d "%~dp0"
.\python_embeded\python.exe amd\runtime.py --disable-api-nodes --cache-lru 20 --disable-smart-memory --disable-pinned-memory --enable-manager --enable-manager-legacy-ui --disable-triton-backend --enable-dynamic-vram --use-flash-attention
if errorlevel 1 exit /b 1
if "%~1"=="" pause
