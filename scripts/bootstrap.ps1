# Portable Bootstrap Script for AgenBroMCP (Windows PowerShell)
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
Write-Host "=== Bootstrapping AgenBroMCP in $RepoRoot ===" -ForegroundColor Cyan

# 1. Ensure uv is available
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

# 2. Ensure Tesseract OCR is available (System or User LocalAppData)
$TessDir = "$env:LOCALAPPDATA\Programs\Tesseract-OCR"
$TessExe = Get-Command tesseract -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $TessExe -and (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")) {
    $TessExe = "C:\Program Files\Tesseract-OCR\tesseract.exe"
}
if (-not $TessExe -and (Test-Path "$TessDir\tesseract.exe")) {
    $TessExe = "$TessDir\tesseract.exe"
}

if (-not $TessExe) {
    Write-Host "Installing portable Tesseract-OCR to $TessDir..." -ForegroundColor Yellow
    $InstallerUrl = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe"
    $TempExe = Join-Path $env:TEMP "tesseract-setup.exe"
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $TempExe
    if (Test-Path "C:\Program Files\7-Zip\7z.exe") {
        & "C:\Program Files\7-Zip\7z.exe" x $TempExe -o"$TessDir" -y | Out-Null
    } else {
        Start-Process -FilePath $TempExe -ArgumentList "/S", "/D=$TessDir" -Wait
    }
    $TessExe = "$TessDir\tesseract.exe"
}

# Ensure rus.traineddata is present
$TessDataDir = Join-Path (Split-Path -Parent $TessExe) "tessdata"
if ((Test-Path $TessDataDir) -and -not (Test-Path (Join-Path $TessDataDir "rus.traineddata"))) {
    Write-Host "Downloading rus.traineddata..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata_fast/raw/main/rus.traineddata" -OutFile (Join-Path $TessDataDir "rus.traineddata")
}

# 3. Create virtual environment and sync dependencies
Write-Host "Syncing Python dependencies via uv..." -ForegroundColor Cyan
uv sync --all-extras

# 4. Install Playwright Chromium browser
Write-Host "Installing Playwright Chromium..." -ForegroundColor Cyan
uv run playwright install chromium

# 5. Create required directories
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "artifacts") | Out-Null

Write-Host "=== Bootstrap complete! Run tests with: uv run pytest ===" -ForegroundColor Green
