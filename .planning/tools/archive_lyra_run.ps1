[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceLog,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [ValidateSet("L0", "L1")]
    [string]$Level,

    [string]$Target = "LyraEditor",
    [string]$Platform = "Win64",
    [string]$Configuration = "Development",

    [ValidateSet("Editor", "PIE", "Standalone", "ListenServer", "DedicatedServer", "Client")]
    [string]$RunMode = "PIE",

    [string]$Map = "",
    [string]$Experience = "",
    [int]$ExitCode,
    [string]$EvidenceRoot = (Join-Path $PSScriptRoot "..\evidence\lyra-5.6.1\runs")
)

$ErrorActionPreference = "Stop"

$source = (Resolve-Path -LiteralPath $SourceLog).Path
$evidence = [System.IO.Path]::GetFullPath($EvidenceRoot).TrimEnd("\", "/")
$runRoot = [System.IO.Path]::GetFullPath((Join-Path $evidence $RunId))
$allowedPrefix = $evidence + [System.IO.Path]::DirectorySeparatorChar

if (-not $runRoot.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "RunId resolved outside EvidenceRoot: $RunId"
}

if (Test-Path -LiteralPath $runRoot) {
    throw "Evidence run already exists and will not be overwritten: $runRoot"
}

[System.IO.Directory]::CreateDirectory($evidence) | Out-Null

$stagingName = ".{0}.incomplete.{1}" -f $RunId, [Guid]::NewGuid().ToString("N")
$stagingRoot = Join-Path $evidence $stagingName
$stagingLog = Join-Path $stagingRoot "raw.log"
$stagingManifest = Join-Path $stagingRoot "manifest.json"
$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)

try {
    [System.IO.Directory]::CreateDirectory($stagingRoot) | Out-Null

    $sourceInfoBefore = Get-Item -LiteralPath $source
    $sourceHashBefore = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()

    Copy-Item -LiteralPath $source -Destination $stagingLog

    $sourceInfoAfter = Get-Item -LiteralPath $source
    $sourceHashAfter = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $copiedHash = (Get-FileHash -LiteralPath $stagingLog -Algorithm SHA256).Hash.ToLowerInvariant()
    $copiedInfo = Get-Item -LiteralPath $stagingLog

    if ($sourceInfoBefore.Length -ne $sourceInfoAfter.Length -or
        $sourceHashBefore -ne $sourceHashAfter) {
        throw "Source log changed while it was being captured. Stop UE and retry."
    }

    if ($copiedInfo.Length -ne $sourceInfoAfter.Length -or $copiedHash -ne $sourceHashAfter) {
        throw "Copied log does not match the source log."
    }

    $baselineManifestHash = $null
    $baselineSummaryPath = Join-Path (Split-Path -Parent $evidence) "baseline-fingerprint.json"
    if (Test-Path -LiteralPath $baselineSummaryPath) {
        $baselineSummary = Get-Content -Raw -Encoding UTF8 -LiteralPath $baselineSummaryPath | ConvertFrom-Json
        $baselineManifestHash = $baselineSummary.manifest_sha256
    }

    $recordedExitCode = $null
    if ($PSBoundParameters.ContainsKey("ExitCode")) {
        $recordedExitCode = $ExitCode
    }

    $manifest = [ordered]@{
        schema_version = "ue-itps.runtime-evidence.v1"
        capture_state = "captured_unassessed"
        run_id = $RunId
        captured_at_utc = [DateTime]::UtcNow.ToString("o")
        capture_tool = [ordered]@{
            name = "archive_lyra_run.ps1"
            sha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        context = [ordered]@{
            level = $Level
            engine = "UE-5.6.1"
            target = $Target
            platform = $Platform
            configuration = $Configuration
            run_mode = $RunMode
            map = $Map
            experience = $Experience
            process_exit_code = $recordedExitCode
            baseline_manifest_sha256 = $baselineManifestHash
        }
        artifact = [ordered]@{
            path = "raw.log"
            media_type = "text/plain"
            size_bytes = [long]$copiedInfo.Length
            sha256 = $copiedHash
            source_file_name = $sourceInfoAfter.Name
            source_last_write_utc = $sourceInfoAfter.LastWriteTimeUtc.ToString("o")
        }
    }

    [System.IO.File]::WriteAllText(
        $stagingManifest,
        (($manifest | ConvertTo-Json -Depth 6) + "`n"),
        $utf8WithoutBom
    )

    Move-Item -LiteralPath $stagingRoot -Destination $runRoot
    Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $runRoot "manifest.json")
}
catch {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
    throw
}
