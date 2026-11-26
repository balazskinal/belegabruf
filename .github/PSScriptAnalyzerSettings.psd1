# PSScriptAnalyzer für installieren.ps1 (Prüf-Workflow „Einrichtung Windows“).
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        # Das Skript spricht mit einem Menschen im PowerShell-Fenster; Write-Host ist dafür gewollt
        # (Ausgaben sollen nicht in einer Pipeline landen, wenn es mit „irm | iex“ läuft).
        'PSAvoidUsingWriteHost'
    )
}
