@echo off
REM ============================================================
REM  inspect_client.bat
REM  Inspecte le client Hystoria V5 et genere un rapport
REM  dans logs\client_inspection.txt
REM
REM  Double-clique sur ce fichier pour lancer l'inspection.
REM ============================================================

cd /d "%~dp0"

echo.
echo === Inspection du client Hystoria V5 ===
echo.

powershell -ExecutionPolicy Bypass -NoProfile -File "tools\inspect_hystoria_client.ps1"

echo.
pause
