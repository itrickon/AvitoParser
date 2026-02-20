@echo off
chcp 1251 >nul
cd /d "%~dp0"

echo Installing dependencies globally...
pip install -U sv-ttk pyinstaller deep_translator playwright openpyxl

echo Installing Chromium (Playwright default path)...
python -m playwright install chromium --force

echo Compiling to SINGLE EXE file...

pyinstaller --clean --noconfirm --distpath=. --name="Avito_Parser" --onefile --windowed --icon="static/AvitoParse_logo.ico" --add-data="static;static" --hidden-import=tkinter --hidden-import=tkinter.ttk --hidden-import=tkinter.messagebox --hidden-import=tkinter.filedialog --hidden-import=sv_ttk --hidden-import=deep_translator --hidden-import=playwright --hidden-import=openpyxl --exclude-module=unittest --exclude-module=pydoc gui.py

if not exist "Avito_Parser.exe" (
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo Cleaning up...
if exist "build" rmdir /s /q "build"
if exist "*.spec" del *.spec

echo Creating desktop shortcut...
set "EXE_PATH=%CD%\Avito_Parser.exe"
set "DESKTOP_PATH=%USERPROFILE%\Desktop"
set "SHORTCUT_NAME=Avito Parser.lnk"
set "ICON_PATH=%CD%\static\AvitoParse_logo.ico"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$WshShell = New-Object -ComObject WScript.Shell; ^
$Shortcut = $WshShell.CreateShortcut('%DESKTOP_PATH%\%SHORTCUT_NAME%'); ^
$Shortcut.TargetPath = '%EXE_PATH%'; ^
$Shortcut.WorkingDirectory = '%CD%'; ^
$Shortcut.IconLocation = '%ICON_PATH%'; ^
$Shortcut.Save();"

echo ====================================================
echo BUILD COMPLETE
echo Executable: %EXE_PATH%
echo Playwright browsers location:
echo %LOCALAPPDATA%\ms-playwright
pause