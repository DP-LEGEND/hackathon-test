# One command that checks the whole project (Windows PowerShell). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1            # everything
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1 -Quick     # skip the production build
# Stop `npm.cmd run dev` first: the build and the dev server share the .next folder.
param([switch]$Quick)

Set-Location (Join-Path $PSScriptRoot "..")
$root = (Get-Location).Path
$results = @()
$fail = $false

function Step([string]$Name, [scriptblock]$Cmd) {
  Write-Host ""
  Write-Host "=== $Name ==="
  & $Cmd
  if ($LASTEXITCODE -eq 0) { $script:results += "PASS  $Name" }
  else { $script:results += "FAIL  $Name"; $script:fail = $true }
}

# Pick Python: an activated environment first, then services\.venv, then the py launcher.
if ($env:VIRTUAL_ENV) { $py = "python" }
elseif (Test-Path "services\.venv\Scripts\python.exe") { $py = Join-Path $root "services\.venv\Scripts\python.exe" }
else { $py = "py" }

if (-not (Test-Path "node_modules")) { Step "npm ci (first run)" { npm.cmd ci } }
Step "Web lint" { npm.cmd run lint }
if (-not $Quick) { Step "Web build + TypeScript" { npm.cmd run build } }
Step "Python tests" { Push-Location services; & $py -m pytest -q; Pop-Location }
Step "Swing JSON contract (sample)" { & $py scripts\check_swing.py data\samples\swing_sample.json }
Step "Python service starts" { & $py -c "import sys; sys.path.insert(0, 'services'); from pipeline.server import app; print('pipeline.server imports OK:', app.title)" }

Write-Host ""
Write-Host "=== Summary ==="
$results | ForEach-Object { Write-Host $_ }
if ($fail) { Write-Host "Some checks failed: scroll up to the first FAIL."; exit 1 }
Write-Host "All checks passed."
exit 0
