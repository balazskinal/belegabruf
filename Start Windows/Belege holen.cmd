@echo off
rem Belege holen - Bedienseite im Browserfenster (Windows). Per Doppelklick starten.
chcp 65001 >nul
rem Das eigentliche Programm liegt im Ordner "programm" daneben.
cd /d "%~dp0..\programm"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1

where uv >nul 2>nul
if errorlevel 1 goto nichteingerichtet

rem Nach einem Update (neues ZIP ausgepackt) fehlt .venv: dann selbst einrichten.
rem Einstellungen, Anmeldungen und Protokolle liegen im Benutzerordner und bleiben.
if exist .venv goto eingerichtet
echo Richte die neue Version ein ... (einmalig, dauert einen Moment)
uv sync --no-dev --quiet
if errorlevel 1 goto selbstfehler
uv run --no-dev --quiet playwright install --no-shell chromium
if errorlevel 1 goto selbstfehler
:eingerichtet

rem Dieses Fenster klein machen; es muss offen bleiben, solange Belegabruf laeuft.
mode con: cols=62 lines=12
uv run --no-dev --quiet belege oberflaeche
if errorlevel 1 pause
exit /b %errorlevel%

:nichteingerichtet
echo Belegabruf ist noch nicht eingerichtet. Bitte zuerst "Einrichten" doppelklicken.
pause
exit /b 1

:selbstfehler
if exist .venv rmdir /s /q .venv
echo Das hat nicht geklappt. Bitte "Einrichten" doppelklicken.
pause
exit /b 1
