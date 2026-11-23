@echo off
REM Launch the Black Bermuda desktop GUI (assumes install_gui.bat has been run).
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" -m bermuda_gui
    exit /b 0
)
echo Virtual environment not found. Run install_gui.bat first.
pause
exit /b 1
