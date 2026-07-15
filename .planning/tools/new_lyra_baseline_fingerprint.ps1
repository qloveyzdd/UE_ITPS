param(
    [string]$ProjectRoot = (Join-Path $PSScriptRoot "..\..\LyraStarterGame"),
    [string]$EvidenceRoot = (Join-Path $PSScriptRoot "..\evidence\lyra-5.6.1")
)

$ErrorActionPreference = "Stop"

$project = (Resolve-Path -LiteralPath $ProjectRoot).Path.TrimEnd("\")
$evidence = [System.IO.Path]::GetFullPath($EvidenceRoot)
$manifestPath = Join-Path $evidence "authoritative-files.sha256"
$summaryPath = Join-Path $evidence "baseline-fingerprint.json"

$excludedDirectoryNames = @(
    ".idea",
    ".vs",
    "Binaries",
    "DerivedDataCache",
    "Intermediate",
    "Saved"
)

$excludedRelativePaths = @(
    ".vsconfig",
    "Build/Scripts/Lyra.Automation.csproj.props",
    "LyraStarterGame.sln"
)

$excludedRelativePrefixes = @(
    "Build/Scripts/obj/"
)

$files = Get-ChildItem -LiteralPath $project -Recurse -File | ForEach-Object {
    $relativePath = $_.FullName.Substring($project.Length + 1).Replace("\", "/")
    $segments = $relativePath.Split("/")

    $hasExcludedPrefix = ($excludedRelativePrefixes | Where-Object { $relativePath.StartsWith($_) }).Count -gt 0

    if (($segments | Where-Object { $_ -in $excludedDirectoryNames }).Count -eq 0 -and
        $relativePath -notin $excludedRelativePaths -and
        -not $hasExcludedPrefix) {
        [pscustomobject]@{
            File = $_
            RelativePath = $relativePath
        }
    }
} | Sort-Object RelativePath

$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
$manifestLines = foreach ($entry in $files) {
    $hash = (Get-FileHash -LiteralPath $entry.File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($entry.RelativePath)"
}

[System.IO.Directory]::CreateDirectory($evidence) | Out-Null
[System.IO.File]::WriteAllText($manifestPath, (($manifestLines -join "`n") + "`n"), $utf8WithoutBom)

$groups = $files | Group-Object { $_.RelativePath.Split("/")[0] } | Sort-Object Name | ForEach-Object {
    [ordered]@{
        name = $_.Name
        file_count = $_.Count
        total_bytes = [long](($_.Group.File | Measure-Object Length -Sum).Sum)
    }
}

$summary = [ordered]@{
    schema_version = 1
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    project = "LyraStarterGame"
    algorithm = "SHA-256"
    manifest_format = "lowercase_sha256, two spaces, forward-slash relative path, LF"
    excluded_directory_names = $excludedDirectoryNames
    excluded_relative_paths = $excludedRelativePaths
    excluded_relative_prefixes = $excludedRelativePrefixes
    file_count = $files.Count
    total_bytes = [long](($files.File | Measure-Object Length -Sum).Sum)
    manifest = "authoritative-files.sha256"
    manifest_sha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    groups = @($groups)
}

[System.IO.File]::WriteAllText(
    $summaryPath,
    (($summary | ConvertTo-Json -Depth 5) + "`n"),
    $utf8WithoutBom
)

$summary | ConvertTo-Json -Depth 5
