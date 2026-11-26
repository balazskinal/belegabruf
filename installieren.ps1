# Belegabruf einrichten oder aktualisieren (Windows) - mit einer Zeile in PowerShell:
#
#   irm https://github.com/balazskinal/belegabruf/releases/latest/download/installieren.ps1 | iex
#
# Was dieses Skript tut (und nichts sonst):
#   1. die neueste Version (bzw. $env:BELEGABRUF_VERSION, z. B. v2.1.1) bei GitHub nachschlagen,
#   2. das ZIP von github.com/balazskinal/belegabruf laden und seine SHA-256-Pruefsumme pruefen
#      (aus der Release-Liste von GitHub bzw. der mitveroeffentlichten .sha256) - ohne Pruefsumme
#      oder bei Abweichung bricht es ab,
#   3. nach %USERPROFILE%\Documents\Belegabruf auspacken. Bei einem Update werden nur die eigenen
#      Programmdateien ersetzt; Einstellungen und Anmeldungen (im Datenordner unter %APPDATA%)
#      bleiben unberuehrt,
#   4. "Belegabruf Windows" starten und den Ordner im Explorer zeigen.
# Keine Adminrechte, keine Aenderungen ausserhalb dieses Ordners (und eines Arbeitsordners in %TEMP%).
#
# Was PowerShell selbst laedt, bekommt kein "Mark of the Web" - so erscheint die Warnung
# "Der Computer wurde durch Windows geschuetzt" nicht, die bei einem im Browser geladenen ZIP kommt.

function Invoke-BelegabrufEinrichtung {
    # Nur in dieser Funktion (mit "irm | iex" liefe es sonst in der Sitzung des Nutzers weiter).
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest ist sonst sehr langsam
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $repo = 'balazskinal/belegabruf'
    $api = "https://api.github.com/repos/$repo/releases"
    $downloads = "https://github.com/$repo/releases/"
    $ziel = if ($env:BELEGABRUF_ZIEL) { $env:BELEGABRUF_ZIEL } else { Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Belegabruf' }
    $version = "$env:BELEGABRUF_VERSION"
    $eigene = @('Belegabruf Mac.command', 'Belegabruf Windows.cmd', 'programm', 'Fehlersuche', 'Doku', '.belegabruf-version')

    function Stop-Einrichtung([string]$text) {
        Write-Host ""
        Write-Host "X $text" -ForegroundColor Red
        Write-Host "Es wurde nichts geaendert. Bei Fragen: https://github.com/$repo"
        throw 'Belegabruf-Einrichtung abgebrochen.'
    }

    function Test-Adresse([string]$adresse) {
        return $adresse.StartsWith("${downloads}download/") -or $adresse.StartsWith("${downloads}latest/download/")
    }

    if ($version -and $version -notmatch '^v\d+\.\d+\.\d+$') {
        Stop-Einrichtung "BELEGABRUF_VERSION='$version' ist keine Versionsnummer wie v2.1.1."
    }
    $profil = [Environment]::GetFolderPath('UserProfile')
    if (-not ([IO.Path]::GetFullPath($ziel)).StartsWith($profil, [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Einrichtung 'Der Zielordner muss in deinem Benutzerordner liegen.'
    }

    $arbeit = Join-Path ([IO.Path]::GetTempPath()) ("belegabruf-einrichten-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $arbeit | Out-Null
    try {
        Write-Host 'Belegabruf einrichten ...'
        # 1. Welche Version, welches ZIP, welche Pruefsumme?
        $releaseUrl = if ($version) { "$api/tags/$version" } else { "$api/latest" }
        $tag = ''; $zipUrl = ''; $erwartet = ''
        try {
            $release = Invoke-RestMethod -Uri $releaseUrl -Headers @{ 'User-Agent' = 'belegabruf' } -UseBasicParsing
        } catch {
            $release = $null
        }
        if ($release) {
            $tag = "$($release.tag_name)"
            if (-not $tag) { Stop-Einrichtung 'GitHub hat keine Version geliefert.' }
            foreach ($gesucht in @('belegabruf.zip', "belegabruf-$tag.zip")) {
                $asset = $release.assets | Where-Object { $_.name -eq $gesucht } | Select-Object -First 1
                if ($asset) {
                    $zipUrl = "$($asset.browser_download_url)"
                    if ("$($asset.digest)" -match '^sha256:([0-9a-f]{64})$') { $erwartet = $Matches[1] }
                    break
                }
            }
            if (-not $zipUrl) { Stop-Einrichtung "In der Version $tag gibt es kein ZIP zum Herunterladen." }
        } elseif (-not $version) {
            $zipUrl = "${downloads}latest/download/belegabruf.zip"
        } else {
            Stop-Einrichtung "Die Version $version gibt es bei GitHub nicht (oder GitHub ist nicht erreichbar)."
        }
        if (-not (Test-Adresse $zipUrl)) { Stop-Einrichtung 'Unerwartete Download-Adresse - aus Sicherheitsgruenden abgebrochen.' }

        if (-not $erwartet -and ($zipUrl -like '*/belegabruf.zip')) {
            try {
                $text = (Invoke-WebRequest -Uri "$zipUrl.sha256" -UseBasicParsing).Content
                if ($text -is [byte[]]) { $text = [Text.Encoding]::ASCII.GetString($text) }
                $erwartet = ("$text".Trim() -split '\s+')[0]
            } catch { $erwartet = '' }
        }
        if ($erwartet -notmatch '^[0-9a-f]{64}$') {
            Stop-Einrichtung 'Fuer diese Version gibt es keine Pruefsumme - ungeprueft wird nichts installiert.'
        }

        # 2. Laden und pruefen
        Write-Host "Lade $(if ($tag) { $tag } else { 'die neueste Version' }) von GitHub ..."
        $zip = Join-Path $arbeit 'belegabruf.zip'
        try {
            Invoke-WebRequest -Uri $zipUrl -OutFile $zip -UseBasicParsing
        } catch {
            Stop-Einrichtung 'Das Herunterladen hat nicht geklappt. Besteht eine Internetverbindung?'
        }
        $ist = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLowerInvariant()
        if ($ist -ne $erwartet) {
            Stop-Einrichtung 'Die Pruefsumme des ZIPs stimmt nicht. Die Datei ist beschaedigt oder nicht die echte - nicht installiert.'
        }
        Write-Host 'OK Pruefsumme stimmt.'

        $aus = Join-Path $arbeit 'aus'
        Expand-Archive -Path $zip -DestinationPath $aus
        $quelle = Get-ChildItem -Path $aus -Directory -Filter 'belegabruf-v*' | Select-Object -First 1
        if (-not $quelle -or -not (Test-Path (Join-Path $quelle.FullName 'Belegabruf Windows.cmd')) -or
            -not (Test-Path (Join-Path $quelle.FullName 'programm'))) {
            Stop-Einrichtung 'Das ZIP hat nicht den erwarteten Inhalt.'
        }
        if (-not $tag) { $tag = $quelle.Name -replace '^belegabruf-', '' }

        # 3. Einspielen: nur die eigenen Eintraege ersetzen
        if ((Test-Path $ziel) -and -not (Test-Path $ziel -PathType Container)) {
            Stop-Einrichtung "'$ziel' ist eine Datei, kein Ordner."
        }
        $kennzeichen = (Test-Path (Join-Path $ziel '.belegabruf-version')) -or (Test-Path (Join-Path $ziel 'Belegabruf Windows.cmd'))
        if ((Test-Path $ziel) -and (Get-ChildItem -Force -Path $ziel | Select-Object -First 1) -and -not $kennzeichen) {
            Stop-Einrichtung "Im Ordner '$ziel' liegen schon andere Dateien, aber kein Belegabruf. Bitte den Ordner umbenennen."
        }
        $laeuft = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -like "*$ziel\programm\*" } | Select-Object -First 1
        if ($laeuft) {
            Stop-Einrichtung "Belegabruf laeuft gerade. Bitte erst beenden (Knopf 'Beenden' im Fenster), dann die Zeile noch einmal."
        }
        New-Item -ItemType Directory -Force -Path $ziel | Out-Null
        Set-Content -Path (Join-Path $quelle.FullName '.belegabruf-version') -Value $tag -Encoding ASCII
        $alt = Join-Path $ziel '.belegabruf-alt'
        if (Test-Path $alt) { Remove-Item -Recurse -Force -LiteralPath $alt }
        New-Item -ItemType Directory -Path $alt | Out-Null
        foreach ($eintrag in $eigene) {
            $pfad = Join-Path $ziel $eintrag
            if (Test-Path -LiteralPath $pfad) { Move-Item -LiteralPath $pfad -Destination $alt }
        }
        try {
            foreach ($eintrag in $eigene) {
                $neu = Join-Path $quelle.FullName $eintrag
                if (Test-Path -LiteralPath $neu) { Move-Item -LiteralPath $neu -Destination $ziel }
            }
        } catch {
            foreach ($eintrag in $eigene) {
                $pfad = Join-Path $ziel $eintrag
                if (Test-Path -LiteralPath $pfad) { Remove-Item -Recurse -Force -LiteralPath $pfad }
                $vorher = Join-Path $alt $eintrag
                if (Test-Path -LiteralPath $vorher) { Move-Item -LiteralPath $vorher -Destination $ziel }
            }
            Stop-Einrichtung 'Das Einspielen hat nicht geklappt; die bisherige Version ist wiederhergestellt.'
        }
        Remove-Item -Recurse -Force -LiteralPath $alt

        if ($kennzeichen) { Write-Host "OK Belegabruf ist auf $tag aktualisiert: $ziel" }
        else { Write-Host "OK Belegabruf $tag ist eingerichtet: $ziel" }
        Write-Host '   Einstellungen und Anmeldungen bleiben im Datenordner (%APPDATA%\belegabruf).'
        Write-Host '   Update spaeter: dieselbe Zeile noch einmal in PowerShell.'

        # 4. Starten
        if ($env:BELEGABRUF_NICHT_STARTEN -ne '1') {
            Start-Process -FilePath 'explorer.exe' -ArgumentList "`"$ziel`""
            Start-Process -FilePath (Join-Path $ziel 'Belegabruf Windows.cmd') -WorkingDirectory $ziel
        }
    } finally {
        Remove-Item -Recurse -Force -LiteralPath $arbeit -ErrorAction SilentlyContinue
    }
}

Invoke-BelegabrufEinrichtung
