@echo off
REM ============================================================
REM Attach Frida hook to a running Dofus Retro process.
REM This redirects the game-server connection to the local proxy.
REM
REM Usage:
REM   1. Launch run_proxy.bat (leave it open)
REM   2. Launch Dofus Retro.exe (but do NOT log in yet)
REM   3. Double-click this file (run_hook.bat)
REM   4. NOW log in through Dofus
REM ============================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] L'environnement virtuel n'existe pas.
    echo          Lance d'abord install.bat pour installer le bot.
    pause
    exit /b 1
)

echo ============================================================
echo Frida hook - redirect Dofus connections to the local proxy
echo ============================================================
echo.
echo Lance Dofus Retro.exe d'abord, puis ce script s'y attache.
echo.

.venv\Scripts\python.exe -m dofus_bot.hook
pause
