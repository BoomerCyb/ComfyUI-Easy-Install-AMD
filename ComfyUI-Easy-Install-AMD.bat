@echo off
cd /d "%~dp0"
setlocal
for %%I in ("%~dp0.") do set "CEI_FOLDER=%%~fI"
for %%I in ("%CEI_FOLDER%") do set "CEI_FOLDER_NAME=%%~nxI"
for %%I in ("%CEI_FOLDER%") do set "CEI_PARENT=%%~dpI"
if /i "%CEI_FOLDER_NAME%"=="ComfyUI-Easy-Install-AMD-Windows" goto rename_download_folder
set "CEI_Title=ComfyUI-Easy-Install-AMD - EZi Desktop Edition"
title %CEI_Title%
color 0A
call :show_logo
echo    ComfyUI-Easy-Install - modified AMD / ROCm edition
echo    Original Easy Install by ivo / Tavris1
echo.
echo    EZi Desktop, Launcher, add-ons and portable Python
echo    Automatic AMD GPU detection and RDNA bundle selection
echo.
echo    Install folder: "%~dp0"
echo.
set "AMD_ROOT=%~dp0."
if exist "%AMD_ROOT%\.amd-installed" goto installed
if not exist "%~dp0Helper-CEI.zip" (
    echo Extract the complete installer ZIP before running this file.
    goto failed
)
echo ::::::::::::::: Preparing Git and Easy Install helpers :::::::::::::::
where git.exe >nul 2>&1
if errorlevel 1 (
    winget.exe install --id Git.Git -e --source winget --scope user --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto failed
)
set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%ProgramFiles%\Git\cmd;%PATH%"
if not exist "%AMD_ROOT%\python_embeded" mkdir "%AMD_ROOT%\python_embeded"
tar.exe -xf "%~dp0Helper-CEI.zip" -C "%AMD_ROOT%"
if errorlevel 1 goto failed
if exist "%AMD_ROOT%\python_embeded\python.exe" goto python_ready
echo.
echo ::::::::::::::: Installing portable Python :::::::::::::::
curl.exe --fail -L --retry 5 -o "%AMD_ROOT%\python-bootstrap.zip" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
if errorlevel 1 goto failed
tar.exe -xf "%AMD_ROOT%\python-bootstrap.zip" -C "%AMD_ROOT%\python_embeded"
if errorlevel 1 goto failed
:python_ready
>"%AMD_ROOT%\python_embeded\python312._pth" (
    echo python312.zip
    echo .
    echo Lib
    echo Lib/site-packages
    echo ../ComfyUI
    echo ../amd
    echo ..
    echo import site
)
if exist "%AMD_ROOT%\python_embeded\Lib\site-packages\pip" goto pip_ready
curl.exe --fail -L --retry 5 -o "%AMD_ROOT%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
if errorlevel 1 goto failed
"%AMD_ROOT%\python_embeded\python.exe" "%AMD_ROOT%\get-pip.py"
if errorlevel 1 goto failed
:pip_ready
echo.
echo ::::::::::::::: Setting up ComfyUI-Easy-Install-AMD :::::::::::::::
"%AMD_ROOT%\python_embeded\python.exe" "%AMD_ROOT%\amd\setup.py"
if errorlevel 1 goto failed
>"%AMD_ROOT%\.amd-installed" echo experimental AMD edition
:installed
echo.
echo ================================================================
echo    ComfyUI-Easy-Install-AMD is ready
echo ================================================================
echo.
echo    Open the EZi Launcher from your desktop shortcut or:
echo    "%AMD_ROOT%\ComfyUI-Easy-Install-AMD Launcher.bat"
echo.
echo    DESKTOP  - ComfyUI EZi, KitchenAttn, SageAttn, FlashAttn
echo    BROWSER  - Launch ComfyUI in your web browser
echo    EASY MENU - Add-ons, models, tools and PyTorch / ROCm bundles
echo.
choice /c LC /n /m "Open EZi Launcher now [L] or close [C]: "
if not errorlevel 2 start "" "%AMD_ROOT%\ComfyUI-Easy-Install-AMD Launcher.bat"
"%AMD_ROOT%\python_embeded\python.exe" "%AMD_ROOT%\amd\cleanup_installer.py"
if errorlevel 1 goto failed
(
    del /q "%~f0"
    exit /b 0
)
:failed
echo Installation failed. See the error above; re-run to retry.
pause
exit /b 1

:show_logo
for /f "delims=" %%E in ('echo prompt $E^| cmd') do set "CEI_ESC=%%E"
set "BGR=%CEI_ESC%[93m"
set "FGR=%CEI_ESC%[92m"
echo.
echo    %BGR%0000000000000000000000000000
echo    %BGR%000000000000%FGR%0000%BGR%000000000000
echo    %BGR%0000%FGR%0000000%BGR%0%FGR%0000%BGR%0%FGR%0000000%BGR%0000
echo    %BGR%0000%FGR%0000000%BGR%0%FGR%0000%BGR%0%FGR%0000000%BGR%0000
echo    %BGR%0000%FGR%0000%BGR%0000%FGR%0000%BGR%0000%FGR%0000%BGR%0000
echo    %BGR%0000%FGR%0000%BGR%0000%FGR%0000%BGR%0000%FGR%0000%BGR%0000
echo    %BGR%0000%FGR%0000%BGR%000000000000%FGR%0000%BGR%0000
echo    %BGR%0000%FGR%00000000000000000000%BGR%0000
echo    %BGR%0000%FGR%00000000000000000000%BGR%0000
echo    %BGR%0000000000000000000000000000
echo    %BGR%0000000 %FGR%EZi  DESKTOP%BGR% 0000000
echo %CEI_ESC%[0m
exit /b 0

:rename_download_folder
if exist "%CEI_PARENT%ComfyUI-Easy-Install-AMD" (
    echo Cannot rename: "%CEI_PARENT%ComfyUI-Easy-Install-AMD" already exists.
    echo Move this extracted installer to another parent folder and run it again.
    pause
    exit /b 1
)
cd /d "%CEI_PARENT%"
if errorlevel 1 goto failed
(
    ren "%CEI_FOLDER%" "ComfyUI-Easy-Install-AMD"
    if errorlevel 1 goto failed
    "%CEI_PARENT%ComfyUI-Easy-Install-AMD\ComfyUI-Easy-Install-AMD.bat"
)
