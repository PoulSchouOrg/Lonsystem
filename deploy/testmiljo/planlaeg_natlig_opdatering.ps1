# Planlægger en natlig opdatering af testdata (kl. 02:30, efter backuppen kl. 00:00) for den bruger der kører
# scriptet. Kræver ikke administrator. Opgaven kører kun, mens brugeren er logget ind på LoenPC.
# Fjern igen med:  Unregister-ScheduledTask -TaskName "LonsystemTestdata" -Confirm:$false
param(
    [string]$TestDir = "C:\LonsystemTest",
    [string]$At = "02:30"
)
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "opdater_testdata.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -TestDir `"$TestDir`""
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "LonsystemTestdata" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Gendanner Lonsystem-testmiljoets database fra nyeste backup (tester samtidig backuppen)" -Force | Out-Null
Write-Host "Natlig opdatering af testdata planlagt kl. $At (opgave: LonsystemTestdata). Log: $TestDir\testmiljo.log"
