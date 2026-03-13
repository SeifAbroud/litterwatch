@echo off
echo Installing dependencies...
py -m pip install pyinstaller watchdog pyperclip --quiet

echo.
echo Building KilloxsLitterbox.exe...
py -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "KilloxsLitterbox" ^
    --hidden-import watchdog.observers ^
    --hidden-import watchdog.observers.winapi ^
    --hidden-import watchdog.events ^
    --hidden-import pyperclip ^
    --collect-all watchdog ^
    killoxs_litterbox.py

echo.
echo Done! Your exe is in the dist\ folder.
pause
