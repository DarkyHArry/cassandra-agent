@echo off
:: ============================================================
:: Cassandra — Launcher para Windows (CMD / Batch)
:: ============================================================
setlocal
cd /d "%~dp0"

set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [*] Preparando ambiente Python em .venv ...
    python -m venv "%VENV%"
    "%VENV%\Scripts\pip.exe" install -q -r requirements.txt
)

if not exist ".env" (
    if exist ".env.example" (
        echo [*] Criando .env a partir de .env.example ...
        copy .env.example .env >nul
    )
)

"%PY%" agent.py %*
