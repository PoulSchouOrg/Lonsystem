# Starter testmiljøet på http://127.0.0.1:8100 (kun på LoenPC selv). Henter først nyeste kode fra 'staging'.
# Produktionen (port 8000) røres ikke. Stop med Ctrl+C eller ved at lukke vinduet.
param(
    [string]$TestDir = "C:\LonsystemTest",
    [string]$Branch = "staging",
    [switch]$NoUpdate
)
$ErrorActionPreference = "Stop"
if (-not $NoUpdate) {
    git -C $TestDir fetch origin
    git -C $TestDir checkout $Branch
    git -C $TestDir pull --ff-only origin $Branch
    & (Join-Path $TestDir ".venv\Scripts\python.exe") -m pip install --quiet -r (Join-Path $TestDir "app\requirements.txt")
}
$envFile = Join-Path $TestDir "app\.env"
if (-not (Select-String -LiteralPath $envFile -Pattern "^LONSYSTEM_ENV=test" -Quiet)) {
    throw "Stop: $envFile mangler LONSYSTEM_ENV=test – starter ikke (det kunne ligne produktion)."
}
Set-Location (Join-Path $TestDir "app")
Write-Host "Testmiljoet koerer paa http://127.0.0.1:8100  (Ctrl+C for at stoppe)"
& (Join-Path $TestDir ".venv\Scripts\python.exe") -m uvicorn main:app --host 127.0.0.1 --port 8100
