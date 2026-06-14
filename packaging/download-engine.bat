@echo off
REM One-time: download the KataGo engine + neural networks next to BadukStudio.exe.
REM Default backend is NVIDIA CUDA 12.8. For other GPUs, see options below.
cd /d "%~dp0"
echo Downloading KataGo engine + networks (this is a few hundred MB)...
BadukStudio.exe --download %*
echo.
echo If you don't have an NVIDIA GPU, re-run with a different backend, e.g.:
echo     download-engine.bat --backend opencl
echo     download-engine.bat --backend eigen     (CPU only, slow)
pause
