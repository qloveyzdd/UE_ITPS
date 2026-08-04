$ErrorActionPreference = "Stop"
$ShowRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ShowRoot

if (-not (Test-Path -LiteralPath (Join-Path $ShowRoot "node_modules"))) {
    npm ci --ignore-scripts --prefer-offline --no-audit --no-fund
}

$Url = "http://localhost:4173"
Start-Job -ScriptBlock {
    param($TargetUrl)
    Start-Sleep -Seconds 2
    Start-Process $TargetUrl
} -ArgumentList $Url | Out-Null

npm run local
