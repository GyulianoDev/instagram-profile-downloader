@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo Ambiente virtual nao encontrado.
    echo Execute: py -m venv .venv
    echo Depois:  .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

start "Instagram Profile Downloader" ".venv\Scripts\pythonw.exe" "interface.py"
