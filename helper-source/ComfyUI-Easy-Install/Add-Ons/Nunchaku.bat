@echo off
cd /d "%~dp0..\"
title ComfyUI-Easy-Install-AMD - Nunchaku Add-On
echo.
echo ================================================================
echo    ComfyUI-Easy-Install-AMD / EZi Add-Ons
echo    Nunchaku - RX 9070 XT only
echo ================================================================
echo.
".\python_embeded\python.exe" amd\install_nunchaku.py
if errorlevel 1 exit /b 1
echo 1. Original Qwen-Image INT4
echo 2. Qwen-Image 2.1 INT4, Turbo and editing
echo 3. Both Qwen model sets
echo 4. Z-Image Turbo INT4
echo 5. FLUX.1 Schnell INT4
echo 6. All model sets
echo 7. Nodes and workflows only - no model downloads
echo 8. Z-Image Turbo FP4 - software FP4 compatibility
echo A. FLUX.2 Klein 9B INT4
echo B. SDXL INT4
echo C. SANA 1.6B INT4
echo D. T5-XXL AWQ INT4 encoder
echo E. LTX2.3 video/audio INT4
choice /c 12345678ABCDE /n /m "Select model set: "
if errorlevel 13 goto ltx2
if errorlevel 12 goto t5
if errorlevel 11 goto sana
if errorlevel 10 goto sdxl
if errorlevel 9 goto flux2
if errorlevel 8 goto fp4
if errorlevel 7 goto done
if errorlevel 6 goto all
if errorlevel 5 goto flux
if errorlevel 4 goto zimage
if errorlevel 3 goto both
if errorlevel 2 goto qwen21
".\python_embeded\python.exe" amd\download_nunchaku_models.py
if errorlevel 1 exit /b 1
goto done
:both
".\python_embeded\python.exe" amd\download_nunchaku_models.py
if errorlevel 1 exit /b 1
:qwen21
".\python_embeded\python.exe" amd\download_nunchaku21_models.py
if errorlevel 1 exit /b 1
goto done
:zimage
".\python_embeded\python.exe" amd\download_nunchaku_extra_models.py zimage
if errorlevel 1 exit /b 1
goto done
:flux
".\python_embeded\python.exe" amd\download_nunchaku_extra_models.py flux
if errorlevel 1 exit /b 1
goto done
:all
".\python_embeded\python.exe" amd\download_nunchaku_models.py
if errorlevel 1 exit /b 1
".\python_embeded\python.exe" amd\download_nunchaku21_models.py
if errorlevel 1 exit /b 1
".\python_embeded\python.exe" amd\download_nunchaku_extra_models.py zimage
if errorlevel 1 exit /b 1
".\python_embeded\python.exe" amd\download_nunchaku_extra_models.py flux
if errorlevel 1 exit /b 1
".\python_embeded\python.exe" amd\download_nunchaku_families.py all
if errorlevel 1 exit /b 1
:fp4
".\python_embeded\python.exe" amd\download_nunchaku_extra_models.py zimage-fp4
if errorlevel 1 exit /b 1
goto done
:flux2
".\python_embeded\python.exe" amd\download_nunchaku_families.py flux2
if errorlevel 1 exit /b 1
goto done
:sdxl
".\python_embeded\python.exe" amd\download_nunchaku_families.py sdxl
if errorlevel 1 exit /b 1
goto done
:sana
".\python_embeded\python.exe" amd\download_nunchaku_families.py sana
if errorlevel 1 exit /b 1
goto done
:t5
".\python_embeded\python.exe" amd\download_nunchaku_families.py t5
if errorlevel 1 exit /b 1
goto done
:ltx2
".\python_embeded\python.exe" amd\download_nunchaku_families.py ltx2
if errorlevel 1 exit /b 1
:done
if "%~1"=="" pause
