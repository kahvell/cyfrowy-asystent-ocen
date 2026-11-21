#requires -Version 5.1
<#
.SYNOPSIS
    Uruchamia Cyfrowego Asystenta Ocen Okresowych na Windows 11 i otwiera przeglądarkę.

.DESCRIPTION
    Wymaga Docker Desktop (albo Podman Desktop / Rancher Desktop z obsługą `docker compose`).
    Skrypt: sprawdza środowisko, tworzy .env z .env.example, buduje i podnosi stos, czeka na
    /health backendu i otwiera http://localhost:3000.

    Uwaga: nigdy nie używaj `docker compose down -v` — flaga -v usuwa wolumen `pgdata`,
    czyli całą bazę (patrz docs/adr/0005-pakowanie-windows-i-migracje.md).

.EXAMPLE
    .\start.ps1
    .\start.ps1 -LocalLlm        # Ollama w kontenerze (profil local-llm)
    .\start.ps1 -NoBuild         # bez przebudowy obrazów (szybszy restart)
#>
[CmdletBinding()]
param(
    [switch]$NoBuild,
    [switch]$LocalLlm,
    [int]$Port = 3000,
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "docker")) {
    throw "Nie znaleziono polecenia 'docker'. Zainstaluj Docker Desktop (https://www.docker.com/products/docker-desktop/) i uruchom go ponownie."
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Silnik Dockera nie odpowiada. Uruchom Docker Desktop i poczekaj, aż wskaże 'Engine running'."
}

$composeVersion = (docker compose version --short) 2>$null
if (-not $composeVersion) {
    throw "Brak 'docker compose' (v2). Zaktualizuj Docker Desktop."
}
Write-Host "docker compose $composeVersion" -ForegroundColor DarkGray

# --- konfiguracja ---
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Utworzono .env z .env.example." -ForegroundColor Yellow
}
if ((Get-Content ".env" -Raw) -match "JWT_SECRET=zmien-mnie") {
    Write-Host "UWAGA: w .env jest domyślny JWT_SECRET - zmien go przed instalacją produkcyjną." -ForegroundColor Yellow
}

# --- start stosu ---
$composeArgs = @()
if ($LocalLlm) { $composeArgs += @("--profile", "local-llm") }
$composeArgs += @("up", "-d")
if (-not $NoBuild) { $composeArgs += "--build" }

Write-Host "Start: docker compose $($composeArgs -join ' ')" -ForegroundColor Cyan
docker compose @composeArgs
if ($LASTEXITCODE -ne 0) { throw "docker compose up zakończył się błędem (kod $LASTEXITCODE)." }

# --- oczekiwanie na backend (migracje Alembica wykonują się przy starcie) ---
Write-Host "Czekam na backend (http://localhost:8000/health)..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        Start-Sleep -Seconds 3
    }
}

if (-not $ready) {
    Write-Host "Backend nie odpowiedział w $TimeoutSec s. Sprawdz log: docker compose logs backend" -ForegroundColor Red
    exit 1
}

$url = "http://localhost:$Port"
Write-Host ""
Write-Host "System gotowy: $url" -ForegroundColor Green
Write-Host "API / OpenAPI:  http://localhost:8000/docs" -ForegroundColor DarkGray
Write-Host "Skrzynka demo:  http://localhost:8025" -ForegroundColor DarkGray
Write-Host "Konta demo (haslo demo123): kazdy pracownik ma konto imie.nazwisko@demo.gov.pl (np. marek.zielinski@demo.gov.pl, anna.kowalska@demo.gov.pl); HR: hr@demo.gov.pl, admin: admin@demo.gov.pl" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Stop:    docker compose down      (BEZ flagi -v!)" -ForegroundColor DarkGray
Write-Host "Backup:  .\scripts\backup-postgres.ps1" -ForegroundColor DarkGray

Start-Process $url
