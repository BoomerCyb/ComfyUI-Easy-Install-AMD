@echo off
setlocal
title ComfyUI-Easy-Install-AMD - ROCm Bundle Manager
cd /d "%~dp0.."
if exist "amd\pending-bundle.txt" del "amd\pending-bundle.txt"
"python_embeded\python.exe" "amd\bundles.py" %*
if errorlevel 1 goto failed
if not exist "amd\pending-bundle.txt" exit /b 0
"python_embeded\python.exe" "amd\bundle_switch.py" --prepare-controller
if errorlevel 1 goto failed
".bundle-controller\python.exe" "amd\bundle_switch.py" --activate
if errorlevel 1 goto failed
if not exist "amd\wtivo-boomercyb-installed.json" goto switched
echo.
echo Rebuilding the compiled AMD nodes for the new PyTorch...
"python_embeded\python.exe" "amd\install_wtivo_group.py" --rebuild
if errorlevel 1 goto rebuild_failed
:switched
pause
exit /b 0
:rebuild_failed
echo.
echo The bundle was switched, but the compiled AMD nodes did not rebuild.
echo Fix the build error above, then reinstall the nodes with WTiVo AMD Download (EZi Settings, WTiVo AMD tab).
pause
exit /b 1
:failed
echo Bundle operation failed; your previous bundle is retained.
pause
exit /b 1
