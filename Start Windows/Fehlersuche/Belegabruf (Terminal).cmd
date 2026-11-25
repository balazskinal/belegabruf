@echo off
rem Belegabruf im Terminal (Menue wie bis Version 1.x, z. B. zur Fehlersuche) (Windows). Per Doppelklick starten.
chcp 65001 >nul
rem Das eigentliche Programm liegt im Ordner "programm" zwei Ebenen hoeher.
cd /d "%~dp0..\..\programm" 2>nul || (
  echo Der Ordner "programm" fehlt neben "Start Windows". Bitte das ZIP vollstaendig auspacken ^(nicht nur den Start-Ordner^).
  pause
  exit /b 1
)
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1

where uv >nul 2>nul
if errorlevel 1 goto nichteingerichtet
if not exist .venv\Scripts\python.exe goto nichteingerichtet

uv run --no-dev --quiet belege start
pause
exit /b %errorlevel%

:nichteingerichtet
echo Belegabruf ist noch nicht eingerichtet. Bitte zuerst "Belegabruf" im Ordner "Start Windows" doppelklicken.
pause
exit /b 1
