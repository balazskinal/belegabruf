@echo off
rem Belege holen - Bedienseite im Browserfenster (Windows). Per Doppelklick starten.
chcp 65001 >nul
rem Das eigentliche Programm liegt im Ordner "programm" daneben.
cd /d "%~dp0..\programm"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1

where uv >nul 2>nul
if errorlevel 1 goto nichteingerichtet
if not exist .venv goto nichteingerichtet

rem Dieses Fenster klein machen; es muss offen bleiben, solange Belegabruf laeuft.
mode con: cols=62 lines=12
uv run --no-dev --quiet belege oberflaeche
exit /b %errorlevel%

:nichteingerichtet
echo Belegabruf ist noch nicht eingerichtet. Bitte zuerst "Einrichten" doppelklicken.
pause
exit /b 1
