@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\LinkedIn Relay.lnk');" ^
  "$s.TargetPath = '%~dp0starten.bat'; $s.Arguments = 'ohne-browser'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Save()"
if errorlevel 1 (
    echo Autostart konnte nicht eingerichtet werden.
) else (
    echo Fertig: LinkedIn Relay startet ab jetzt automatisch, wenn Windows hochfaehrt.
    echo Zum Entfernen: Windows-Taste + R, "shell:startup" eingeben, Verknuepfung loeschen.
)
pause
