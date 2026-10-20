@echo off
chcp 65001 >nul
cd /d "%~dp0"
title LinkedIn Relay
if not exist ".venv\Scripts\python.exe" (
    echo Bitte zuerst "installieren.bat" doppelklicken.
    pause
    exit /b 1
)
if not exist ".env" (
    echo Die Einstellungsdatei .env fehlt. Bitte "installieren.bat" erneut ausfuehren.
    pause
    exit /b 1
)
echo LinkedIn Relay laeuft. Dieses Fenster bitte offen lassen (minimieren ist ok).
echo Oberflaeche im Browser: http://localhost:5000
echo.
if /i "%~1"=="ohne-browser" (
    ".venv\Scripts\python.exe" -m linkedin_relay start --ohne-browser
) else (
    ".venv\Scripts\python.exe" -m linkedin_relay start
)
echo.
echo Die App wurde beendet.
pause
