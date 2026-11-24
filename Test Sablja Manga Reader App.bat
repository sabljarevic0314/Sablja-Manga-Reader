@echo off
rem Double-click to test the current source code (not the installed app).
rem Your installed library is only ever COPIED, never changed.
setlocal
cd /d "%~dp0"
title Sablja Manga Reader App - test from source

if not exist ".venv\Scripts\python.exe" (
    echo Setting up Python for the first time, this takes a minute...
    py -3 -m venv .venv 2>nul || python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

set "REAL=%LOCALAPPDATA%\Programs\SabljaReader\data\db.json"
if not exist "data" mkdir "data"
if not exist "%REAL%" goto run

echo.
echo   1 = Test with a fresh copy of my installed library
echo   2 = Keep the test library from last time
echo.
choice /c 12 /n /m "Choose 1 or 2: "
if errorlevel 2 goto run
if exist "data\db.json" copy /y "data\db.json" "data\db.json.bak" >nul
copy /y "%REAL%" "data\db.json" >nul
echo Copied. Your real library stays untouched.

:run
".venv\Scripts\python.exe" -c "import flet" 2>nul || ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
echo Starting Sablja Manga Reader App (new interface)...
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
    echo.
    echo The app stopped with an error. The details are above and in data\errors.log
    pause
)
