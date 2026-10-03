@echo off
setlocal
cd /d "%~dp0.."
if exist "amd\pending-bundle.txt" del "amd\pending-bundle.txt"
"python_embeded\python.exe" "amd\bundles.py" %*
if errorlevel 1 goto failed
if not exist "amd\pending-bundle.txt" exit /b 0
"python_embeded\python.exe" "amd\bundle_switch.py" --prepare-controller
if errorlevel 1 goto failed
".bundle-controller\python.exe" "amd\bundle_switch.py" --activate
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo Bundle operation failed; your previous bundle is retained.
pause
exit /b 1
