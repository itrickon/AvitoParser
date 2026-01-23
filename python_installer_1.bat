@echo off
chcp 1251 >nul
echo.
echo ====================================================
echo =                   Python Install                 =
echo ====================================================
echo.

echo.
echo Installing python...
powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.14.2/python-3.14.2-amd64.exe' -OutFile 'python_setup.exe'"
python_setup.exe

echo.
echo Removing Python installation files...
del /f /q python_setup.exe
echo Python setup file has been removed.
echo.
pause