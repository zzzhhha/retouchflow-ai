$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    python -m venv (Join-Path $repoRoot ".venv")
}

& $python -m pip install --index-url https://pypi.org/simple -r (Join-Path $repoRoot "local-ai-service\requirements.txt")
& $python -m uvicorn app.main:app --app-dir (Join-Path $repoRoot "local-ai-service") --host 127.0.0.1 --port 8765
