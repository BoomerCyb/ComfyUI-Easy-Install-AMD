@echo off
cd /d "%~dp0"
setlocal
set "CEI_WORKER="
if /I "%~1"=="CEI_WORKER" set "CEI_WORKER=1"
rem Fix from upstream 3.27.2: PowerShell 7 modules broke the checks below.
set "PSModulePath="
rem Checks from upstream 3.26.0: no Administrator rights, no network path, no system or read-only folder.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "if(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){exit 10}else{exit 0}"
if %errorlevel% equ 10 goto drop_admin
del "%TEMP%\CEI_AMD_deelevate.flag" >nul 2>&1
set "CEI_HOME=%~dp0"
if "%CEI_HOME:~0,2%"=="\\" (
    echo Network paths ^(UNC^) are not supported.
    echo Copy the installer folder to a local drive and run it again.
    pause
    exit /b 1
)
set "CEI_ROOT=%CD%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$r=[IO.Path]::GetFullPath($env:CEI_ROOT).TrimEnd('\')+'\'; if($r -ieq ($env:SystemDrive+'\')){exit 1}; foreach($d in @($env:SystemRoot,$env:ProgramFiles,${env:ProgramFiles(x86)},$env:ProgramW6432)){if($d -and $r.StartsWith($d.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){exit 1}}; exit 0"
if errorlevel 1 (
    echo Cannot install into system folders like Program Files, Windows or the drive root C:\.
    echo Move the installer folder to another folder, for example D:\AI\, and run it again.
    pause
    exit /b 1
)
set "CEI_TEST=.cei_test_%RANDOM%%RANDOM%"
(md "%CEI_TEST%") 2>nul
(echo test>"%CEI_TEST%\write.tmp") 2>nul
if not exist "%CEI_TEST%\write.tmp" (
    rd /s /q "%CEI_TEST%" 2>nul
    echo No permission to create folders or files here.
    echo Move the installer folder to a folder you own, for example in your user folder or on another drive.
    pause
    exit /b 1
)
rd /s /q "%CEI_TEST%" 2>nul
for %%I in ("%~dp0.") do set "CEI_FOLDER=%%~fI"
for %%I in ("%CEI_FOLDER%") do set "CEI_FOLDER_NAME=%%~nxI"
for %%I in ("%CEI_FOLDER%") do set "CEI_PARENT=%%~dpI"
if /i "%CEI_FOLDER_NAME%"=="ComfyUI-Easy-Install-AMD-Windows" goto rename_download_folder
rem The installer window (Helper-CEI.ps1, from upstream 3.30.0) runs this file again as CEI_WORKER and reads its log.
rem amd\setup.py sends the same ##STEP lines and corrects the plan: steps per stage.
set "CEI_BAT=%~f0"
set "CEI_GUI=%~dp0Helper-CEI.ps1"
set "CEI_STAGES=Preparing|PyTorch and packages|Custom nodes|Finishing"
set "CEI_PLAN=6|3|60|4"
if defined CEI_WORKER (
    set "PYTHONUNBUFFERED=1"
    set "PIP_PROGRESS_BAR=raw"
    goto gui_done
)
if /I "%~1"=="CEI_CONSOLE" goto gui_done
if not exist "%CEI_GUI%" goto gui_done
call :start_gui
if defined CEI_GUI_OK exit /b 0
set "CEI_GUI_FAILED=1"
start "" cmd.exe /d /c ""%CEI_BAT%" CEI_CONSOLE"
exit /b 0
:gui_done
set "CEI_Title=ComfyUI-Easy-Install-AMD - EZi Desktop Edition"
title %CEI_Title%
if defined CEI_WORKER goto skip_banner
color 0C
call :show_logo
echo    ComfyUI-Easy-Install - modified AMD / ROCm edition
echo    Original Easy Install by ivo / Tavris1
echo.
echo    EZi Desktop, Launcher, add-ons and portable Python
echo    Automatic AMD GPU detection and RDNA bundle selection
echo.
echo    Install folder: "%~dp0"
echo.
:skip_banner
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$c=0; if($env:CEI_ROOT -cmatch '[^\x00-\x7F]'){$c+=1}; if($env:USERPROFILE -cmatch '[^\x00-\x7F]'){$c+=2}; exit $c"
set "CEI_NA=%errorlevel%"
if not "%CEI_NA%"=="0" (
    if "%CEI_NA%"=="1" echo WARNING: The install path contains non-English characters. Installation problems are possible.
    if "%CEI_NA%"=="3" echo WARNING: The install path contains non-English characters. Installation problems are possible.
    if "%CEI_NA%"=="2" echo WARNING: Your Windows user folder name contains non-English characters. Installation problems are possible.
    if "%CEI_NA%"=="3" echo WARNING: Your Windows user folder name contains non-English characters. Installation problems are possible.
    echo Recommended: a short English-only path, for example D:\AI\
    echo.
    if defined CEI_WORKER echo ##WARN^|The install path or user folder has non-English characters: problems are possible
    if not defined CEI_WORKER timeout /t 3 /nobreak >nul
)
set "AMD_ROOT=%~dp0."
if exist "%AMD_ROOT%\.amd-installed" goto installed
if not exist "%~dp0Helper-CEI.zip" (
    echo Extract the complete installer ZIP before running this file.
    goto failed
)
echo ::::::::::::::: Preparing Git and Easy Install helpers :::::::::::::::
call :step 1 "Git"
where git.exe >nul 2>&1
if errorlevel 1 (
    winget.exe install --id Git.Git -e --source winget --scope user --accept-package-agreements --accept-source-agreements
    if errorlevel 1 goto failed
)
set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%ProgramFiles%\Git\cmd;%PATH%"
if not exist "%AMD_ROOT%\python_embeded" mkdir "%AMD_ROOT%\python_embeded"
call :step 1 "Helper files"
tar.exe -xf "%~dp0Helper-CEI.zip" -C "%AMD_ROOT%"
if errorlevel 1 goto failed
call :step 1 "Portable Python"
if exist "%AMD_ROOT%\python_embeded\python.exe" goto python_ready
echo.
echo ::::::::::::::: Installing portable Python :::::::::::::::
curl.exe --fail -L --retry 5 -o "%AMD_ROOT%\python-bootstrap.zip" "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
if errorlevel 1 goto download_failed
rem SHA-256 of python.org's python-3.12.10-embed-amd64.zip (its MD5, fe8ef205f2e9c3ba44d0cf9954e1abd3, is on python.org)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try{$h=(Get-FileHash -LiteralPath ($env:AMD_ROOT + '\python-bootstrap.zip') -Algorithm SHA256 -ErrorAction Stop).Hash}catch{Write-Host $_.Exception.Message;exit 2};if($h -eq '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'){exit 0}else{Write-Host ('Actual SHA256: '+$h);exit 1}"
set "HASH_RC=%errorlevel%"
if %HASH_RC% equ 2 (
    echo.
    echo Could not calculate the checksum of the Python download. The download itself may be fine.
    echo Check your PowerShell and antivirus settings, then run this installer again from a normal CMD window.
    goto failed
)
if %HASH_RC% neq 0 (
    del "%AMD_ROOT%\python-bootstrap.zip" >nul 2>&1
    echo.
    echo Python archive checksum does not match: the download may be corrupted or modified.
    goto failed
)
tar.exe -xf "%AMD_ROOT%\python-bootstrap.zip" -C "%AMD_ROOT%\python_embeded"
if errorlevel 1 goto failed
if not exist "%AMD_ROOT%\python_embeded\python.exe" (
    echo.
    echo Failed to extract python.exe. Your antivirus may have blocked Python files:
    echo check Windows Security, Protection history, allow them and run this installer again.
    goto failed
)
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
call :step 1 "pip"
if exist "%AMD_ROOT%\python_embeded\Lib\site-packages\pip" goto pip_ready
curl.exe --fail -L --retry 5 -o "%AMD_ROOT%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
if errorlevel 1 curl.exe --fail -L --retry 5 -o "%AMD_ROOT%\get-pip.py" "https://raw.githubusercontent.com/pypa/get-pip/main/public/get-pip.py"
if errorlevel 1 goto download_failed
"%AMD_ROOT%\python_embeded\python.exe" "%AMD_ROOT%\get-pip.py"
if errorlevel 1 goto failed
rem Fix from upstream 3.27.3: stop here if pip did not end up working.
"%AMD_ROOT%\python_embeded\python.exe" -I -m pip --version
if errorlevel 1 (
    echo.
    echo Pip did not install correctly. Check the messages above and your internet connection.
    goto failed
)
:pip_ready
echo.
echo ::::::::::::::: Setting up ComfyUI-Easy-Install-AMD :::::::::::::::
"%AMD_ROOT%\python_embeded\python.exe" "%AMD_ROOT%\amd\setup.py"
if errorlevel 1 goto failed
>"%AMD_ROOT%\.amd-installed" echo experimental AMD edition
:installed
if defined CEI_WORKER goto worker_finish
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
rem (goto) ends this batch first, so deleting it does not print "The batch file cannot be found".
(goto) 2>nul & del /q "%~f0"
:worker_finish
call :step 4 "Cleaning up"
"%AMD_ROOT%\python_embeded\python.exe" "%AMD_ROOT%\amd\cleanup_installer.py"
if errorlevel 1 goto failed
echo ##DONE
(goto) 2>nul & del /q "%~f0"
:download_failed
echo.
echo Download failed. Check your date and time, Windows updates and antivirus HTTPS scanning.
if defined CEI_WORKER echo ##FATAL^|Download failed^|Check your date and time, Windows updates and antivirus HTTPS scanning.
:failed
echo Installation failed. See the error above; re-run to retry.
pause
exit /b 1

:drop_admin
rem Started as Administrator: start again through Explorer, which runs it as the normal user. If it comes back
rem elevated anyway (Explorer itself elevated), try runas with basic user rights once, then give up.
if /i "%~1"=="CEI_NOADMIN" (
    echo This installer cannot run with Administrator rights.
    echo Start it with a normal double-click, NOT with Run as administrator.
    pause
    exit /b 1
)
echo Administrator rights detected. Restarting without them...
if exist "%TEMP%\CEI_AMD_deelevate.flag" (
    del "%TEMP%\CEI_AMD_deelevate.flag" >nul 2>&1
    runas.exe /trustlevel:0x20000 "cmd.exe /c \"\"%~f0\" CEI_NOADMIN\""
    if errorlevel 1 (
        echo Failed to restart without Administrator rights.
        echo Start this file with a normal double-click, NOT with Run as administrator.
        pause
        exit /b 1
    )
    exit /b 0
)
(echo.>"%TEMP%\CEI_AMD_deelevate.flag") 2>nul
"%SystemRoot%\explorer.exe" "%~f0"
exit /b 0

:start_gui
set "CEI_GUI_OK="
set "CEI_GUI_FLAG=%TEMP%\CEI_AMD_gui_%RANDOM%%RANDOM%.flag"
del "%CEI_GUI_FLAG%" "%CEI_GUI_FLAG%.cancel" "%CEI_GUI_FLAG%.fail" >nul 2>&1
echo Starting the installer window...
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%CEI_GUI%" -BatPath "%CEI_BAT%" -Flag "%CEI_GUI_FLAG%"
for /l %%i in (1,1,10) do (
    if exist "%CEI_GUI_FLAG%" goto start_gui_ok
    if exist "%CEI_GUI_FLAG%.fail" goto start_gui_fail
    timeout /t 1 /nobreak >nul
)
type nul > "%CEI_GUI_FLAG%.cancel"
timeout /t 2 /nobreak >nul
if exist "%CEI_GUI_FLAG%" goto start_gui_ok
:start_gui_fail
del "%CEI_GUI_FLAG%.fail" >nul 2>&1
echo The installer window could not start. Continuing in the console...
echo.
exit /b 0
:start_gui_ok
del "%CEI_GUI_FLAG%" >nul 2>&1
set "CEI_GUI_OK=1"
exit /b 0

:step
if defined CEI_WORKER echo ##STEP^|%~1^|%~2
exit /b 0

:show_logo
for /f "delims=" %%E in ('echo prompt $E^| cmd') do set "CEI_ESC=%%E"
set "BGR=%CEI_ESC%[93m"
set "FGR=%CEI_ESC%[91m"
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
