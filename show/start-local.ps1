$ErrorActionPreference = "Stop"
$showRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $showRoot
if (-not (Test-Path -LiteralPath (Join-Path $showRoot "node_modules"))) {
    npm ci
}
npm run dev
