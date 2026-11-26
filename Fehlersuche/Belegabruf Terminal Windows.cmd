@echo off
rem Belegabruf im Terminal (Menue wie bis Version 1.x, z. B. zur Fehlersuche) (Windows). Per Doppelklick starten.
chcp 65001 >nul
rem Das eigentliche Programm liegt im Ordner "programm" eine Ebene hoeher (neben "Fehlersuche").
cd /d "%~dp0..\programm" 2>nul || (
  echo Der Ordner "programm" fehlt neben "Fehlersuche". Bitte das ZIP vollstaendig auspacken und
  echo den Starter im ausgepackten Ordner doppelklicken ^(nicht einzeln herausziehen^).
  pause
  exit /b 1
)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1

where uv >nul 2>nul
if errorlevel 1 goto nichteingerichtet
if not exist .venv\Scripts\python.exe goto nichteingerichtet

uv run --locked --no-dev --quiet belege start
pause
exit /b %errorlevel%

:nichteingerichtet
echo Belegabruf ist noch nicht eingerichtet. Bitte zuerst "Belegabruf Windows" doppelklicken ^(liegt oben im Ordner^).
pause
exit /b 1
