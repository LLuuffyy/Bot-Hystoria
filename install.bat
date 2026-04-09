@echo off
REM ============================================================
REM  dofus_bot - Installation one-click pour Windows
REM  Double-clique sur ce fichier pour tout installer.
REM ============================================================

echo.
echo === Installation du bot Dofus Hystoria ===
echo.

cd /d "%~dp0"

REM Verifier que Python est installe
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo          Telecharge-le sur https://www.python.org/downloads/
    echo          Coche "Add Python to PATH" pendant l'installation.
    pause
    exit /b 1
)

echo [1/3] Creation de l'environnement virtuel...
if not exist .venv (
    python -m venv .venv
    if errorlevel 1 (
        echo [ERREUR] Impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
)

echo [2/3] Activation et mise a jour de pip...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip

echo [3/3] Installation des dependances...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] L'installation des dependances a echoue.
    pause
    exit /b 1
)

echo.
echo === Installation terminee ! ===
echo.
echo Prochaines etapes :
echo   1. Copie .env.example vers .env et edite-le si besoin
echo   2. Modifie ton fichier hosts pour rediriger play-hystoria.net
echo      vers 127.0.0.1 (voir dofus_bot\README.md)
echo   3. Double-clique sur run_proxy.bat pour lancer le bot
echo.
pause
