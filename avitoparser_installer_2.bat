@echo off
chcp 1251 >nul
echo.
echo ====================================================
echo =                   Avito Parser                   =
echo ====================================================
echo.
echo This tool is for educational and research purposes only.
echo Use responsibly and in compliance with applicable laws.
echo.

echo.
echo Installing dependencies...
pip install sv-ttk
pip install pyinstaller
pip install deep_translator 
pip install playwright
pip install openpyxl
pip install pandas
pip install pillow
pip install pytesseract
pip install asyncio

echo.
echo Installing Playwright browser...
playwright install chromium

echo.
echo Compiling EXE...
pyinstaller --clean --noconfirm ^
--distpath=. ^
--name="AvitoParser" ^
--onedir ^
--windowed ^
--icon="static/Avito_logo.ico" ^
--add-data="static;static" ^
--add-data="%LOCALAPPDATA%\ms-playwright\chromium-*;ms-playwright" ^
--runtime-hook=playwright_runtime_hook.py ^
--exclude-module=unittest ^
--exclude-module=pydoc ^
gui.py

echo.
echo Moving files from AvitoParser folder to root...
if exist "AvitoParser" (
    echo Moving main executable...
    move "AvitoParser\AvitoParser.exe" "." >nul 2>nul
    
    echo Moving _internal folder...
    if exist "AvitoParser\_internal" (
        move "AvitoParser\_internal" "." >nul 2>nul
    )
    
    echo Moving other files...
    for %%F in ("AvitoParser\*.*") do (
        if not "%%F"=="AvitoParser\_internal" if not "%%F"=="AvitoParser\AvitoParser.exe" (
            move "%%F" "." >nul 2>nul
        )
    )
    
    echo Cleaning up temporary folders...
    rmdir /s /q "AvitoParser" 2>nul
    rmdir /s /q build 2>nul
    del *.spec 2>nul
    
    echo Files moved successfully!
) else (
    echo ERROR: AvitoParser folder was not created!
)

echo.
echo Creating necessary directories...
if not exist "avito_parse_results" mkdir "avito_parse_results"
if not exist "avito_phones_playwright" mkdir "avito_phones_playwright"
if not exist "avito_phones_playwright\phones" mkdir "avito_phones_playwright\phones"
if not exist "avito_phones_playwright\debug" mkdir "avito_phones_playwright\debug"
if not exist "static" mkdir "static"

echo.
echo Checking for Avito logo...
if not exist "static\Avito_logo.ico" (
    echo WARNING: Avito logo not found in static folder!
    echo Please place Avito_logo.ico in the static folder.
)

echo.
echo Creating desktop shortcut...
set "EXE_PATH=%CD%\AvitoParser.exe"
set "DESKTOP_PATH=%USERPROFILE%\Desktop"
set "SHORTCUT_NAME=Avito Parser.lnk"
set "ICON_PATH=%CD%\static\Avito_logo.ico"

:: Проверяем, существует ли EXE
if not exist "%EXE_PATH%" (
    echo ERROR: AvitoParser.exe not found!
    echo Trying alternative location...
    if exist "dist\AvitoParser.exe" (
        move "dist\AvitoParser.exe" "." >nul 2>nul
        if exist "%EXE_PATH%" (
            echo EXE found and moved!
        ) else (
            echo ERROR: Cannot find AvitoParser.exe
            pause
            exit /b 1
        )
    ) else (
        echo ERROR: Cannot find AvitoParser.exe anywhere!
        pause
        exit /b 1
    )
)

:: Создаем ярлык через PowerShell
echo Creating shortcut via PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$WshShell = New-Object -ComObject WScript.Shell; ^
$Shortcut = $WshShell.CreateShortcut('%DESKTOP_PATH%\%SHORTCUT_NAME%'); ^
$Shortcut.TargetPath = '%EXE_PATH%'; ^
$Shortcut.WorkingDirectory = '%CD%'; ^
if (Test-Path '%ICON_PATH%') { ^
    $Shortcut.IconLocation = '%ICON_PATH%'; ^
} ^
$Shortcut.Description = 'Avito Parser - Educational Tool'; ^
$Shortcut.Save(); ^
Write-Host 'Shortcut created!'"

:: Проверяем создание
if exist "%DESKTOP_PATH%\%SHORTCUT_NAME%" (
    echo Desktop shortcut created: %SHORTCUT_NAME%
) else (
    echo WARNING: Failed to create desktop shortcut
    echo You can create it manually from AvitoParser.exe
)

echo.
echo ====================================================
echo Installation completed!
echo.
echo IMPORTANT: You need to install Tesseract OCR separately:
echo 1. Download from: https://github.com/UB-Mannheim/tesseract/wiki
echo 2. Install to: C:\Program Files\Tesseract-OCR\
echo.
echo Launch AvitoParser from the desktop shortcut or AvitoParser.exe
echo ====================================================
echo.
pause