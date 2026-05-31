# Build both EXEs and produce a release zip with checksums.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$version = (python -c "from citadel_version import VERSION_STRING; print(VERSION_STRING)").Trim()
$cleanVersion = ($version -replace '\s+', '_')
Write-Host "[Citadel] Packaging release v$version..." -ForegroundColor Yellow

& "$PSScriptRoot\build_citadel_pbo_builder.ps1"
& "$PSScriptRoot\build_citadel_pbo_inspector.ps1"

$stagingRoot = Join-Path $repoRoot "releases"
if (-not (Test-Path $stagingRoot)) { New-Item -ItemType Directory -Path $stagingRoot | Out-Null }
$releaseDir = Join-Path $stagingRoot "Citadel_PBO_Tools_${cleanVersion}"
if (Test-Path $releaseDir) { Remove-Item $releaseDir -Recurse -Force }
New-Item -ItemType Directory -Path $releaseDir | Out-Null

Copy-Item -Path (Join-Path $repoRoot "dist\Citadel_PBO_Builder.exe") -Destination $releaseDir
Copy-Item -Path (Join-Path $repoRoot "dist\Citadel_PBO_Inspector.exe") -Destination $releaseDir
Copy-Item -Path (Join-Path $repoRoot "README.md") -Destination $releaseDir
Copy-Item -Path (Join-Path $repoRoot "CHANGELOG.md") -Destination $releaseDir
Copy-Item -Path (Join-Path $repoRoot "LICENSE.txt") -Destination $releaseDir

# Checksums
$hashLines = @()
Get-ChildItem $releaseDir -File | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    $hashLines += "$hash  $($_.Name)"
}
$hashLines | Out-File -FilePath (Join-Path $releaseDir "SHA256SUMS.txt") -Encoding utf8

$zipPath = Join-Path $stagingRoot "Citadel_PBO_Tools_${cleanVersion}.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path "$releaseDir\*" -DestinationPath $zipPath

Write-Host "[Citadel] Release archive: $zipPath" -ForegroundColor Green
