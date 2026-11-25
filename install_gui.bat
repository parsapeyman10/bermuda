@echo off
setlocal EnableExtensions
title Black Bermuda GUI - Installer
cd /d "%~dp0"

echo ==================================================
echo   Black Bermuda - Desktop GUI - Installer
echo   Black Bermuda - install this tool on this PC
echo ==================================================
echo.

REM ---- 1) locate Python 3.10+ --------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( where python3 >nul 2>nul && set "PY=python3" )
if not defined PY (
    echo [ERROR] Python 3.10+ was not found.
    echo         Install it from https://www.python.org/downloads/
    echo         and tick "Add python.exe to PATH" during setup.
    pause
    exit /b 1
)
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" || (
    echo [ERROR] Python 3.10 or newer is required.
    pause
    exit /b 1
)
echo [1/4] Python OK:
%PY% --version
echo.

REM ---- 2) virtual environment ----------------------------------
set "VENV=%~dp0.venv"
if not exist "%VENV%\Scripts\python.exe" (
    echo [2/4] Creating virtual environment in "%VENV%" ...
    %PY% -m venv "%VENV%" || (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Reusing existing virtual environment: "%VENV%"
)
echo.

REM ---- 3) dependencies ------------------------------------------
echo [3/4] Installing dependencies (PyQt6, numpy, pandas, scipy,
echo       opencv, matplotlib, Flask). This can take a few minutes...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -r "%~dp0bermuda_gui\requirements.txt" || (
    echo [ERROR] Dependency installation failed.
    echo         Check your internet connection and try again.
    pause
    exit /b 1
)

REM ---- 4) verify + desktop shortcut ------------------------------
echo [4/4] Verifying the application...
"%VENV%\Scripts\python.exe" -c "import bermuda_gui; print('bermuda_gui', bermuda_gui.__version__, '- OK')" || (
    echo [ERROR] The application did not import correctly.
    pause
    exit /b 1
)
echo Creating Desktop shortcut "Black Bermuda GUI"...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Black Bermuda GUI.lnk'; $s = $ws.CreateShortcut($lnk); $s.TargetPath = '%VENV%\Scripts\pythonw.exe'; $s.Arguments = '-m bermuda_gui'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0bermuda_gui\assets\icon.ico,0'; $s.Description = 'Black Bermuda - candle replay simulator (research/education)'; $s.Save()" || echo [WARN] Shortcut could not be created; see command below.
echo.
echo ==================================================
echo   Done!
echo.
echo   Start the app:
echo     - double-click "Black Bermuda GUI" on the Desktop, or
echo     - run:  "%VENV%\Scripts\pythonw.exe" -m bermuda_gui
echo.
echo   Research / education tool. No trading edge is claimed;
echo   detector parameters are not validated out-of-sample.
echo ==================================================
pause
