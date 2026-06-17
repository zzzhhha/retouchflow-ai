$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    python -m venv (Join-Path $repoRoot ".venv")
}

& $python -m pip install --index-url https://pypi.org/simple -r (Join-Path $repoRoot "local-ai-service\requirements.txt")
$env:PYTHONPATH = Join-Path $repoRoot "local-ai-service"
& $python -m unittest discover (Join-Path $repoRoot "local-ai-service\tests")
& $python -m compileall (Join-Path $repoRoot "local-ai-service")
