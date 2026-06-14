@echo off
REM Build the Baduk Studio Windows bundle -> dist\BadukStudio\BadukStudio.exe
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip || exit /b 1
python -m pip install -r requirements.txt pyinstaller || exit /b 1

python -m PyInstaller --noconfirm baduk_studio.spec || exit /b 1

echo.
echo Built: dist\BadukStudio\BadukStudio.exe
echo Fetch the engine once next to it:  dist\BadukStudio\BadukStudio.exe --download
endlocal
