# Opsætter testmiljøet ÉN gang (kan køres igen uden skade).
# Henter koden (branch 'staging') til en separat mappe, laver et separat Python-miljø og en .env
# der markerer testmiljøet og IKKE indeholder mailoplysninger. Rører ikke produktionen.
#
# Kør fra en almindelig PowerShell på LoenPC:  powershell -ExecutionPolicy Bypass -File opsaet_testmiljo.ps1
param(
    [string]$TestDir = "C:\LonsystemTest",
    [string]$Branch = "staging",
    [string]$Repo = "https://github.com/PoulSchouOrg/Lonsystem.git"
)
$ErrorActionPreference = "Stop"

# 1. Koden
if (Test-Path -LiteralPath (Join-Path $TestDir ".git")) {
    git -C $TestDir fetch origin
    git -C $TestDir checkout $Branch
    git -C $TestDir pull --ff-only origin $Branch
} else {
    git clone --branch $Branch $Repo $TestDir
}

# 2. Separat Python-miljø (pakker til test påvirker aldrig produktionens Python)
$venvPy = Join-Path $TestDir ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    $basePy = (& py -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1)
    if (-not $basePy) { $basePy = (Get-Command python -ErrorAction Stop).Source }
    & $basePy -m venv (Join-Path $TestDir ".venv")
}
& $venvPy -m pip install --quiet -r (Join-Path $TestDir "app\requirements.txt")

# 3. .env: testmarkering, egen nøgle, INGEN SMTP (der må aldrig gå e-mail fra testmiljøet)
$envFile = Join-Path $TestDir "app\.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    $lines = @(
        "LONSYSTEM_ENV=test",
        "SESSION_SECRET=$secret",
        "# Ingen SMTP_*-linjer: testmiljoet sender aldrig e-mail"
    )
    # UTF-8 uden BOM, ellers læses første linje forkert
    [System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding $false))
}

Write-Host ""
Write-Host "Testmiljoet er sat op i $TestDir (branch $Branch)."
Write-Host "Naeste skridt: opdater_testdata.ps1 (kopi af nyeste backup), derefter start_testmiljo.ps1."
