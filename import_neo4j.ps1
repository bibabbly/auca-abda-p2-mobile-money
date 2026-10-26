# Section 3.2 step 2: full offline import into the default neo4j database.
# Neo4j must be STOPPED. Run from the project folder:
#   .\import_neo4j.ps1
param(
    [string]$Database = "neo4j",
    [string]$ImportDir = "$PSScriptRoot\import"
)
. "$PSScriptRoot\neo4j_env.ps1"
New-Item -ItemType Directory -Force "$PSScriptRoot\logs" | Out-Null

$started = Get-Date
$watch = [Diagnostics.Stopwatch]::StartNew()
# Java writes progress/warnings to stderr; print it as plain text instead of PowerShell errors.
$ErrorActionPreference = "Continue"
& "$env:NEO4J_HOME\bin\neo4j-admin.bat" database import full $Database `
    --overwrite-destination=true `
    --id-type=integer `
    --nodes=Customer="$ImportDir\customers.csv" `
    --nodes=Account="$ImportDir\accounts.csv" `
    --nodes=Device="$ImportDir\devices.csv" `
    --relationships=OWNS="$ImportDir\owns.csv" `
    --relationships=USED_DEVICE="$ImportDir\used_device.csv" `
    --relationships=TRANSFER="$ImportDir\transfers.csv" `
    --report-file="$PSScriptRoot\logs\neo4j_import_report.txt" 2>&1 | ForEach-Object { "$_" }
$exit = $LASTEXITCODE
$watch.Stop()

$seconds = [math]::Round($watch.Elapsed.TotalSeconds, 1)
Write-Host ""
Write-Host "neo4j-admin import exit code: $exit   import seconds: $seconds"
if ($Database -eq "neo4j") {
    New-Item -ItemType Directory -Force "$PSScriptRoot\results" | Out-Null
    @{ database = $Database; started_cat = $started.ToString("yyyy-MM-ddTHH:mm:sszzz");
       import_seconds = $seconds; exit_code = $exit } |
        ConvertTo-Json | Set-Content "$PSScriptRoot\results\neo4j_import.json" -Encoding utf8
}
exit $exit
