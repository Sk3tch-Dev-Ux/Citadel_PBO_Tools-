# Build Citadel_PBO_Builder.exe with PyInstaller.
# Run from the repository root: .\scripts\build_citadel_pbo_builder.ps1

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "[Citadel] Building Citadel PBO Builder..." -ForegroundColor Magenta

$icon = Join-Path $repoRoot "assets\citadel.ico"
$iconArgs = @()
if (Test-Path $icon) { $iconArgs = @("--icon", $icon) }

# Note: PyInstaller writes progress to stderr. Do NOT use 2>&1 — PowerShell 5.1
# wraps native stderr in ErrorRecords and sets $? to false even on success.
# Instead let PyInstaller print directly and check the real exit code.
& python -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name "Citadel_PBO_Builder" `
    --hidden-import citadel.gui.builder_app `
    --hidden-import citadel.gui.options_dialog `
    --hidden-import citadel.gui.widgets `
    --hidden-import citadel.core.theme `
    --hidden-import citadel.core.assets `
    --add-data "assets;assets" `
    --exclude-module tkinterdnd2 `
    @iconArgs `
    citadel_pbo_builder.py

$exit = $LASTEXITCODE
if ($exit -ne 0) {
    Write-Host "[Citadel] PyInstaller failed for Builder (exit $exit)." -ForegroundColor Red
    exit $exit
}

$exePath = Join-Path $repoRoot "dist\Citadel_PBO_Builder.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "[Citadel] Builder EXE not produced. Check the build log above." -ForegroundColor Red
    exit 1
}
Write-Host "[Citadel] Builder built: $exePath" -ForegroundColor Green
