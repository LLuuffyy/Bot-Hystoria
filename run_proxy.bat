@echo off
REM ============================================================
REM  dofus_bot - Lancement du proxy MITM
REM  Double-clique pour demarrer le proxy, puis lance ton
REM  client Dofus. Ctrl+C dans cette fenetre pour arreter.
REM ============================================================

cd /d "%~dp0"

if not exist .venv (
    echo [ERREUR] L'environnement virtuel n'existe pas.
    echo          Lance d'abord install.bat pour installer le bot.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m dofus_bot --proxy
pause
