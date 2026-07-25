<#
Builds dist/planeopt/planeopt.exe from a clean Windows virtualenv.

Run from Windows (PowerShell), not WSL — PyInstaller cannot cross-compile; a
Windows .exe must be frozen by a Windows interpreter.

    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

The build venv (.venv-win) is separate from the WSL .venv on purpose: the two
hold platform-specific wheels and must never share a directory.
#>
param(
    [string]$Python = "python",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $repo ".venv-win"
$vpy = Join-Path $venv "Scripts\python.exe"

Push-Location $repo
try {
    if (-not (Test-Path $vpy)) {
        Write-Host "==> creating build venv at $venv"
        & $Python -m venv $venv
    }

    if (-not $SkipInstall) {
        Write-Host "==> installing planeopt + pyinstaller"
        & $vpy -m pip install --upgrade pip --quiet
        # No --editable: the frozen build must consume the package exactly as a
        # user would install it, which is what proves the package data travels.
        # .[gui] — the desktop app ships in the bundle; the cad extra does not.
        & $vpy -m pip install ".[gui]" pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "dependency install failed" }
    }

    Write-Host "==> freezing"
    & $vpy -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\planeopt.spec
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

    $exe = Join-Path $repo "dist\planeopt\planeopt.exe"
    Write-Host "==> smoke test: startup"
    & $exe --version
    & $exe info
    if ($LASTEXITCODE -ne 0) { throw "the built exe does not start" }

    # A real evaluation, not just startup: this is the only thing that proves the
    # CasADi/IPOPT libraries, the NeuralFoil weights, the airfoil database, the
    # prop tables and the report template all resolved inside the bundle.
    Write-Host "==> smoke test: end-to-end evaluation"
    $smoke = Join-Path $env:TEMP "planeopt-smoke"
    & $exe run missions\endurance_sample.py -a aircraft\vtail_sample --runs-dir $smoke
    if ($LASTEXITCODE -ne 0) { throw "the built exe cannot complete a run" }
    $report = Get-ChildItem $smoke -Recurse -Filter report.html |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $report) { throw "the run produced no report.html" }
    Write-Host "    report: $($report.FullName)"

    # The GUI cannot be launched headlessly here, but its absence from the
    # bundle must not pass silently — `info` reports what actually imported.
    if (-not (& $exe info | Select-String -Quiet "gui extra       available")) {
        throw "the bundle has no working GUI (planeopt info says it is unavailable)"
    }

    $size = "{0:N0} MB" -f ((Get-ChildItem (Join-Path $repo "dist\planeopt") -Recurse |
        Measure-Object -Property Length -Sum).Sum / 1MB)
    Write-Host "==> built $exe ($size)"
}
finally {
    Pop-Location
}
