$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$activate = Join-Path $PSScriptRoot "venv\Scripts\Activate.ps1"
if (-not (Test-Path -LiteralPath $activate)) {
    throw "Python virtual environment not found. Create it with: python -m venv venv"
}
. $activate

$distIndex = Join-Path $PSScriptRoot "frontend\dist\index.html"
if (-not (Test-Path -LiteralPath $distIndex)) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Frontend build is missing and Node.js/npm are not installed. Install Node.js LTS, reopen PowerShell, then run this script again."
    }
    Push-Location (Join-Path $PSScriptRoot "frontend")
    try {
        npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally {
        Pop-Location
    }
}

$url = "http://127.0.0.1:8000"
$browserJob = Start-Job -ArgumentList $url -ScriptBlock {
    param($siteUrl)
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            Invoke-WebRequest -Uri "$siteUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
            Start-Process $siteUrl
            return
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
}

try {
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
}
finally {
    Stop-Job -Job $browserJob -ErrorAction SilentlyContinue
    Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
}
