@echo off
cd /d "%~dp0"
.\python_embeded\python.exe amd\runtime.py --auto-launch --disable-api-nodes --cache-lru 20 --disable-smart-memory --disable-pinned-memory --enable-manager --enable-manager-legacy-ui --disable-triton-backend --enable-dynamic-vram --use-ck-attention
if errorlevel 1 goto failed
if "%~1"=="" pause
exit /b 0
:failed
rem Keep the window open on errors too, unless a caller passed an argument (EZi uses NoPause).
if "%~1"=="" pause
exit /b 1
