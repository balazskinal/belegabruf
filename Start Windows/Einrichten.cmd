@echo off
rem Belegabruf einrichten (Windows). Per Doppelklick starten.
chcp 65001 >nul
rem Das eigentliche Programm liegt im Ordner "programm" daneben.
cd /d "%~dp0..\programm"
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
set PYTHONUTF8=1

echo Belegabruf wird eingerichtet. Das dauert beim ersten Mal ein paar Minuten.
echo.

where uv >nul 2>nul
if errorlevel 1 (
  echo Hole das Hilfsprogramm uv ^(von astral.sh^) ...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
  echo uv konnte nicht installiert werden. Besteht eine Internetverbindung?
  pause
  exit /b 1
)

echo Hole Python und die noetigen Bausteine ...
uv sync --no-dev --quiet
if errorlevel 1 ( echo Das hat nicht geklappt. & pause & exit /b 1 )

echo Hole den Browser ^(Chromium^) ...
uv run --no-dev playwright install chromium
if errorlevel 1 ( echo Der Browser konnte nicht geladen werden. & pause & exit /b 1 )

uv run --no-dev belege einrichten
echo Fertig.
pause
