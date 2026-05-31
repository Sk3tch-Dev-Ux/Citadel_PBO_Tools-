# Build Citadel_PBO_Inspector.exe with PyInstaller.
# Run from the repository root: .\scripts\build_citadel_pbo_inspector.ps1

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "[Citadel] Building Citadel PBO Inspector..." -ForegroundColor Magenta

$icon = Join-Path $repoRoot "assets\citadel.ico"
$iconArgs = @()
if (Test-Path $icon) { $iconArgs = @("--icon", $icon) }

# Note: PyInstaller writes progress to stderr. Do NOT use 2>&1 — PowerShell 5.1
# wraps native stderr in ErrorRecords and sets $? to false even on success.
# tkinterdnd2 is intentionally excluded — its bundled tkdnd 2.9.5 DLL is
# compiled for Tcl/Tk 8.6 but PyInstaller bundles whatever Tcl ships with the
# current Python (Tcl 9.x on Microsoft Store Python 3.13). The DnD load
# always fails inside the EXE, so we drop the bundle and rely on Browse +
# Reload PBO. The Inspector entry point still tries DnD at runtime in
# source-mode for users on Tcl/Tk 8.6 Pythons.
& python -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name "Citadel_PBO_Inspector" `
    --hidden-import citadel.gui.inspector_app `
    --hidden-import citadel.inspector.viewer `
    --hidden-import citadel.inspector.p3d_meta `
    --hidden-import citadel.core.theme `
    --hidden-import citadel.core.assets `
    --add-data "assets;assets" `
    --exclude-module tkinterdnd2 `
    @iconArgs `
    citadel_pbo_inspector.py

$exit = $LASTEXITCODE
if ($exit -ne 0) {
    Write-Host "[Citadel] PyInstaller failed for Inspector (exit $exit)." -ForegroundColor Red
    exit $exit
}

$exePath = Join-Path $repoRoot "dist\Citadel_PBO_Inspector.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "[Citadel] Inspector EXE not produced. Check the build log above." -ForegroundColor Red
    exit 1
}
Write-Host "[Citadel] Inspector built: $exePath" -ForegroundColor Green
