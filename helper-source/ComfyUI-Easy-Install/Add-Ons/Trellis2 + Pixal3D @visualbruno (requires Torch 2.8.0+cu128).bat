@echo off
echo This NVIDIA add-on has no verified Windows ROCm build in this edition.
echo It has been retained as a compatibility entry; nothing will be installed.
if "%~1"=="" pause
exit /b 1
