@echo off
setlocal
title Push NOVA Dashboard to GitHub
cd /d "%~dp0"

echo ======================================================================
echo   Push NOVA Dashboard to GitHub
echo ======================================================================
echo.

:: 1. Auto-detect Git and ensure all Git directories are in PATH
if exist "C:\Program Files\Git\cmd" (
    set "PATH=C:\Program Files\Git\cmd;C:\Program Files\Git\bin;C:\Program Files\Git\mingw64\bin;%PATH%"
) else if exist "C:\Program Files (x86)\Git\cmd" (
    set "PATH=C:\Program Files (x86)\Git\cmd;C:\Program Files (x86)\Git\bin;C:\Program Files (x86)\Git\mingw64\bin;%PATH%"
) else if exist "%LOCALAPPDATA%\Programs\Git\cmd" (
    set "PATH=%LOCALAPPDATA%\Programs\Git\cmd;%LOCALAPPDATA%\Programs\Git\bin;%LOCALAPPDATA%\Programs\Git\mingw64\bin;%PATH%"
)

:: 2. Auto-detect Python
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    py -c "import sys" >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=py"
    ) else (
        python -c "import sys" >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=python"
        )
    )
)
if not defined PYTHON_EXE (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%D\python.exe" (
            "%%D\python.exe" -c "import sys" >nul 2>nul
            if not errorlevel 1 set "PYTHON_EXE=%%D\python.exe"
        )
    )
)
if not defined PYTHON_EXE (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

"%PYTHON_EXE%" github_push.py

if errorlevel 1 (
    echo.
    echo [ERROR] Git push encountered an issue.
    pause
    exit /b 1
)

echo.
pause
