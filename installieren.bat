@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ===== LinkedIn Relay: Installation =====
echo.

set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python ist noch nicht installiert. Es wird jetzt installiert ...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo Automatische Installation nicht moeglich. Bitte Python von https://www.python.org/downloads/ laden
        echo und beim Installieren das Haekchen "Add python.exe to PATH" setzen.
        pause
        exit /b 1
    )
    echo.
    echo Python wurde installiert. Bitte dieses Fenster schliessen
    echo und "installieren.bat" noch einmal doppelklicken.
    pause
    exit /b 0
)

echo [1/4] Arbeitsumgebung anlegen ...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv || goto fehler
)

echo [2/4] Programmteile laden (dauert einige Minuten) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto fehler

echo [3/4] Browser fuer die Grafiken laden ...
".venv\Scripts\python.exe" -m playwright install chromium || goto fehler

echo [4/4] Einstellungen vorbereiten ...
if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo Installation abgeschlossen.
echo Jetzt oeffnet sich die Datei mit den Einstellungen im Editor.
echo Bitte ausfuellen, speichern und danach "starten.bat" doppelklicken.
echo.
pause
notepad ".env"
exit /b 0

:fehler
echo.
echo FEHLER: Die Installation ist nicht durchgelaufen.
echo Bitte ein Foto oder eine Kopie dieses Fensters an Claude schicken.
pause
exit /b 1
