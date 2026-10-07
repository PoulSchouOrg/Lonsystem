# Gendanner testmiljøets database fra den NYESTE backup-zip (som produktionen allerede laver 4 gange i døgnet).
# Produktionens database røres ikke. Fungerer samtidig som en natlig gendannelsestest af backuppen:
#   - fejler hvis zip'en mangler lonsystem.db eller databasen er beskadiget
#   - advarer hvis nyeste backup er ældre end 36 timer (så er backup-opgaven holdt op)
#
# Exit-kode: 0 = ok, 1 = fejl, 2 = ok men backuppen er for gammel.
param(
    [string]$TestDir = "C:\LonsystemTest",
    [string]$BackupDir = $env:LONSYSTEM_BACKUP_DIR,
    [int]$MaxAgeHours = 36
)
$ErrorActionPreference = "Stop"
$logFile = Join-Path $TestDir "testmiljo.log"
function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -LiteralPath $logFile -Value $line
    Write-Host $line
}

if (-not $BackupDir) {
    Write-Log "FEJL: backup-mappen er ukendt. Angiv -BackupDir eller saet LONSYSTEM_BACKUP_DIR."
    exit 1
}
$zip = Get-ChildItem -LiteralPath $BackupDir -Filter "lonsystem_*.zip" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) {
    Write-Log "FEJL: ingen backup-zip fundet i $BackupDir"
    exit 1
}
$tooOld = ((Get-Date) - $zip.LastWriteTime).TotalHours -gt $MaxAgeHours
if ($tooOld) {
    Write-Log ("ADVARSEL: nyeste backup ({0}) er {1} timer gammel - tjek backup-opgaven!" -f $zip.Name, [int]((Get-Date) - $zip.LastWriteTime).TotalHours)
}

# Stop testserveren, hvis den kører (port 8100) – produktionen på 8000 røres ikke
$wasRunning = $false
$listen = Get-NetTCPConnection -LocalPort 8100 -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    $listen | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
    $wasRunning = $true
    Start-Sleep -Seconds 2
}

# Pak ud til en midlertidig mappe og tjek databasen, før den kopieres ind
$tmp = Join-Path $env:TEMP "lonsystem_testdata"
Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $zip.FullName -DestinationPath $tmp -Force
$src = Join-Path $tmp "lonsystem.db"
if (-not (Test-Path -LiteralPath $src)) {
    Write-Log "FEJL: lonsystem.db mangler i $($zip.Name)"
    exit 1
}
$py = Join-Path $TestDir ".venv\Scripts\python.exe"
$check = & $py -c "import sqlite3,sys`ntry: print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])`nexcept Exception as e: print(e)" $src 2>&1
if ($check -ne "ok") {
    Write-Log "FEJL: databasen i $($zip.Name) er beskadiget: $check"
    exit 1
}

$dbDir = Join-Path $TestDir "app\database"
Get-ChildItem -LiteralPath $dbDir -Filter "lonsystem.db*" | Remove-Item -Force
Copy-Item -LiteralPath $src -Destination (Join-Path $dbDir "lonsystem.db")
$stamp = [datetime]::ParseExact($zip.BaseName.Substring(10), "yyyy-MM-dd_HH-mm", $null).ToString("dd-MM-yyyy 'kl.' HH:mm")
[System.IO.File]::WriteAllText((Join-Path $dbDir "TESTDATA_SOURCE.txt"), $stamp, (New-Object System.Text.UTF8Encoding $false))
Remove-Item -LiteralPath $tmp -Recurse -Force

Write-Log "Testdata gendannet fra $($zip.Name) (integritet ok)"
if ($wasRunning) {
    Start-Process powershell -WindowStyle Minimized -ArgumentList @("-ExecutionPolicy", "Bypass", "-File",
        (Join-Path $PSScriptRoot "start_testmiljo.ps1"), "-TestDir", $TestDir)
    Write-Log "Testserveren er startet igen"
}
if ($tooOld) { exit 2 }
exit 0
