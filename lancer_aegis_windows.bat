@echo off
title Aegis Trader — MetaTrader 5
color 0A

echo ============================================
echo   AEGIS TRADER — Demarrage sur MetaTrader 5
echo ============================================
echo.

REM ── Verifie que Python est installe ──────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python non trouve. Installe Python 3.11 depuis python.org
    pause
    exit /b 1
)

REM ── Installe les dependances si besoin ───────────────────────
echo [1/3] Verification des dependances Python...
pip install -q MetaTrader5 anthropic python-dotenv requests flask pandas numpy rich psutil python-telegram-bot
echo       OK

REM ── Verifie que MetaTrader 5 est ouvert ──────────────────────
echo [2/3] Verifie que MetaTrader 5 est ouvert et connecte...
echo       (Si MT5 n est pas ouvert, ouvre-le maintenant et connecte-toi au compte demo)
echo.
timeout /t 5 /nobreak >nul

REM ── Lance le bot ─────────────────────────────────────────────
echo [3/3] Lancement du bot Aegis avec broker MT5...
echo.

REM Change vers le dossier du script
cd /d "%~dp0"

REM Configure le broker MT5
set BROKER_TYPE=mt5

REM Charge les variables du fichier .env si present
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
    )
)

REM Lance le scanner en boucle (redemarrage automatique en cas d erreur)
:loop
echo [%time%] Bot Aegis demarre...
python auto_scanner.py
echo.
echo [%time%] Bot arrete. Redemarrage dans 10 secondes... (Ctrl+C pour quitter)
timeout /t 10 /nobreak >nul
goto loop
