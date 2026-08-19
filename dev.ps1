# Starts the FastAPI backend and the Vite dev server together.
# Ctrl+C stops both.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$backend = Start-Process -PassThru -NoNewWindow -FilePath 'pwsh' -ArgumentList @(
  '-NoProfile', '-Command',
  "Set-Location '$root/backend'; .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
)
$frontend = Start-Process -PassThru -NoNewWindow -FilePath 'pwsh' -ArgumentList @(
  '-NoProfile', '-Command',
  "Set-Location '$root/frontend'; npm run dev"
)

Write-Host 'RatKitchen running. API on http://127.0.0.1:8000, UI on http://127.0.0.1:5173'
try {
  Wait-Process -Id $backend.Id, $frontend.Id
} finally {
  foreach ($p in @($backend, $frontend)) {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
}
