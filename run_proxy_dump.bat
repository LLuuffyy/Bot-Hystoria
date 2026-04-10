@echo off
REM ============================================================
REM  dofus_bot - Proxy MITM en mode DUMP
REM  Identique a run_proxy.bat mais affiche tous les paquets
REM  qui transitent (utile pour analyser un protocole inconnu).
REM ============================================================

cd /d "%~dp0"

if not exist .venv (
    echo [ERREUR] L'environnement virtuel n'existe pas.
    echo          Lance d'abord install.bat pour installer le bot.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m dofus_bot --proxy --dump
pause
