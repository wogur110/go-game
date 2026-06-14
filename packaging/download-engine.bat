@echo off
REM One-time: download the KataGo engine + neural networks next to BadukStudio.exe.
REM Default backend on Windows is OpenCL (works with just your GPU driver).
cd /d "%~dp0"
echo Downloading KataGo engine + networks (a few hundred MB)...
BadukStudio.exe --download %*
echo.
echo Backends: default OpenCL (recommended). Others:
echo     download-engine.bat --backend cuda12.8   (faster, but needs CUDA 12 + cuDNN 9 installed)
echo     download-engine.bat --backend eigen      (CPU only, slow)
pause
