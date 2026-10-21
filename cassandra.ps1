<#
.SYNOPSIS
    Cassandra — Launcher para Windows (PowerShell)
.EXAMPLE
    .\cassandra.ps1
    .\cassandra.ps1 --web
    .\cassandra.ps1 --allow-shell
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$VenvDir = Join-Path $ScriptDir ".venv"
$PyExe = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Test-Path $PyExe)) {
    Write-Host "[*] Preparando ambiente virtual em .venv ..." -ForegroundColor Cyan
    python -m venv $VenvDir
    $PipExe = Join-Path $VenvDir "Scripts\pip.exe"
    & $PipExe install -q -r (Join-Path $ScriptDir "requirements.txt")
}

$EnvFile = Join-Path $ScriptDir ".env"
if (-not (Test-Path $EnvFile)) {
    $EnvExample = Join-Path $ScriptDir ".env.example"
    if (Test-Path $EnvExample) {
        Write-Host "[*] Criando .env a partir de .env.example ..." -ForegroundColor Cyan
        Copy-Item $EnvExample $EnvFile
    }
}

& $PyExe (Join-Path $ScriptDir "agent.py") @args
