#requires -Version 5.1
<#
.SYNOPSIS
    Backup i odtworzenie bazy PostgreSQL (wolumen `pgdata`) dla Cyfrowego Asystenta Ocen.

.DESCRIPTION
    Uruchom PRZED każdą aktualizacją obrazu. Zrzut robi `pg_dump` WEWNĄTRZ kontenera i jest
    kopiowany przez `docker compose cp` — przekierowanie `>` w PowerShellu psuje dane binarne.

    Obok zrzutu zapisywane są metadane (wersja aplikacji z git + rewizja Alembica), żeby
    wiedzieć, z jaką wersją schematu kopia jest zgodna, oraz kopia .env (zawiera JWT_SECRET —
    traktuj plik jak sekret).

    Zrzut zawiera dane osobowe (RODO): przechowuj go zaszyfrowany i zgodnie z polityką urzędu.

.EXAMPLE
    .\scripts\backup-postgres.ps1
    .\scripts\backup-postgres.ps1 -OutDir D:\kopie -KeepDays 90
    .\scripts\backup-postgres.ps1 -Restore D:\kopie\app_20261121_180000.dump
#>
[CmdletBinding()]
param(
    [string]$OutDir = "backup",
    [int]$KeepDays = 30,
    [string]$Restore = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path $PSScriptRoot -Parent)

$DbService = "db"
$DbUser = "app"
$DbName = "app"
$ContainerDump = "/tmp/asystent_backup.dump"
$ContainerRestore = "/tmp/asystent_restore.dump"

function Invoke-Compose {
    param([string[]]$ComposeArgs, [string]$What)
    docker compose @ComposeArgs
    if ($LASTEXITCODE -ne 0) { throw "$What - docker compose zakończył się błędem (kod $LASTEXITCODE)." }
}

function Get-AlembicRevision {
    $rev = docker compose exec -T $DbService psql -U $DbUser -d $DbName -tAc "SELECT version_num FROM alembic_version" 2>$null
    if ($LASTEXITCODE -ne 0) { return "nieznana" }
    return ($rev | Out-String).Trim()
}

if ($Restore) {
    # --- odtworzenie: rollback po nieudanej aktualizacji ---
    if (-not (Test-Path $Restore)) { throw "Nie znaleziono pliku: $Restore" }
    if (-not $Force) {
        $answer = Read-Host "Odtworzenie NADPISZE obecną bazę danymi z '$Restore'. Wpisz TAK, aby kontynuować"
        if ($answer -ne "TAK") { Write-Host "Przerwano."; exit 0 }
    }

    Write-Host "Zatrzymuję backend i frontend (żeby nikt nie pisał do bazy w trakcie)..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("stop", "backend", "frontend") -What "Zatrzymanie aplikacji"

    Invoke-Compose -ComposeArgs @("cp", (Resolve-Path $Restore).Path, "${DbService}:$ContainerRestore") -What "Kopiowanie zrzutu do kontenera"
    Write-Host "Odtwarzam bazę..." -ForegroundColor Cyan
    # --clean --if-exists: usuwa istniejące obiekty przed odtworzeniem;
    # pg_restore zwraca niezerowy kod także przy samych ostrzeżeniach (np. o rolach) - dlatego ostrzegamy, ale nie przerywamy
    docker compose exec -T $DbService pg_restore -U $DbUser -d $DbName --clean --if-exists $ContainerRestore
    if ($LASTEXITCODE -ne 0) {
        Write-Host "pg_restore zwrócił kod $LASTEXITCODE - przejrzyj komunikat powyżej (ostrzeżenia są zwykle nieszkodliwe)." -ForegroundColor Yellow
    }
    Invoke-Compose -ComposeArgs @("exec", "-T", $DbService, "rm", "-f", $ContainerRestore) -What "Sprzątanie"

    Write-Host "Startuję aplikację (migracje Alembica wykonają się same)..." -ForegroundColor Cyan
    Invoke-Compose -ComposeArgs @("start", "backend", "frontend") -What "Start aplikacji"

    Write-Host "Odtworzono. Sprawdz: http://localhost:8000/health oraz logowanie." -ForegroundColor Green
    exit 0
}

# --- backup ---
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$target = Join-Path $OutDir "app_$stamp.dump"

Write-Host "Zrzut bazy do $target ..." -ForegroundColor Cyan
Invoke-Compose -ComposeArgs @("exec", "-T", $DbService, "sh", "-c", "pg_dump -U $DbUser -Fc -f $ContainerDump $DbName") -What "pg_dump"
Invoke-Compose -ComposeArgs @("cp", "${DbService}:$ContainerDump", $target) -What "Kopiowanie zrzutu"
Invoke-Compose -ComposeArgs @("exec", "-T", $DbService, "rm", "-f", $ContainerDump) -What "Sprzątanie"

$appVersion = "brak git"
if (Get-Command git -ErrorAction SilentlyContinue) {
    $appVersion = (git rev-parse --short HEAD 2>$null)
}
$revision = Get-AlembicRevision

@(
    "data:               $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "wersja aplikacji:   $appVersion"
    "rewizja Alembica:   $revision"
    "baza:               $DbName (uzytkownik $DbUser)"
    "zrzut:              $target"
) | Out-File -FilePath "$target.meta.txt" -Encoding utf8

if (Test-Path ".env") {
    Copy-Item ".env" (Join-Path $OutDir ".env.$stamp") -Force
    Write-Host "Skopiowano .env (sekret - JWT_SECRET)." -ForegroundColor DarkGray
}

$sizeMb = [math]::Round((Get-Item $target).Length / 1MB, 2)
Write-Host "Gotowe: $target ($sizeMb MB), rewizja Alembica: $revision" -ForegroundColor Green

# rotacja starych kopii
$cutoff = (Get-Date).AddDays(-$KeepDays)
$old = Get-ChildItem -Path $OutDir -Filter "app_*.dump*" | Where-Object { $_.LastWriteTime -lt $cutoff }
if ($old) {
    $old | Remove-Item -Force
    Write-Host "Usunięto kopii starszych niż $KeepDays dni: $($old.Count)" -ForegroundColor DarkGray
}
