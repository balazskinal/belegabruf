@echo off
rem Belegabruf (Windows). Per Doppelklick starten.
rem Richtet sich beim ersten Mal und nach einem Update selbst ein; jeder Schritt nur, wenn noetig:
rem uv holen, Bausteine (uv sync), Browser (Chromium), dann das Fenster "Belegabruf" oeffnen.
chcp 65001 >nul
rem Das eigentliche Programm liegt im Ordner "programm" daneben.
cd /d "%~dp0..\programm"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1

rem a) Hilfsprogramm uv
where uv >nul 2>nul
if not errorlevel 1 goto uvda
echo Belegabruf wird eingerichtet. Das dauert beim ersten Mal ein paar Minuten.
echo Hole das Hilfsprogramm uv ^(von astral.sh^) ...
powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo uv konnte nicht installiert werden. Besteht eine Internetverbindung?
  pause
  exit /b 1
)
:uvda

rem b) Python und Bausteine: fehlt die Umgebung, oder ist uv.lock neuer (Update)?
if not exist .venv\Scripts\python.exe goto sync
.venv\Scripts\python.exe -m belegabruf.startpruefung umgebung >nul 2>nul
if not errorlevel 1 goto browser
:sync
echo Richte die neue Version ein ... ^(Python und die noetigen Bausteine^)
uv sync --no-dev --quiet
if errorlevel 1 goto syncfehler
type nul > .venv\.belegabruf-sync

rem c) Browser (Chromium, ohne Headless Shell): nur wenn er fuer diese Playwright-Version fehlt.
rem    Die Pruefung liest nur eine Datei, sie startet Playwright nicht.
:browser
.venv\Scripts\python.exe -m belegabruf.startpruefung browser >nul 2>nul
if not errorlevel 1 goto start
echo Hole den Browser ^(Chromium^) ...
uv run --no-dev --quiet playwright install --no-shell chromium
if errorlevel 1 (
  echo Der Browser konnte nicht geladen werden. Besteht eine Internetverbindung? Dann einfach noch einmal doppelklicken.
  pause
  exit /b 1
)

rem d) Fenster "Belegabruf". Dieses Fenster klein machen; es muss offen bleiben, solange Belegabruf laeuft.
:start
mode con: cols=62 lines=12
uv run --no-dev --quiet belege oberflaeche
if errorlevel 1 pause
exit /b %errorlevel%

:syncfehler
if exist .venv rmdir /s /q .venv
echo Das hat nicht geklappt. Besteht eine Internetverbindung? Dann einfach noch einmal doppelklicken.
pause
exit /b 1
