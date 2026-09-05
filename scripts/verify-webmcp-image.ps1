# Verify the production demo image includes WebMCP Agent Hub (no Render deploy).
# Uses :8011 by default so it does not clash with a long-running tunnel on :8010.
$ErrorActionPreference = 'Stop'
$tag = if ($args[0]) { $args[0] } else { 'muefs-demo:webmcp' }
$port = if ($env:MUEFS_VERIFY_PORT) { [int]$env:MUEFS_VERIFY_PORT } else { 8011 }
$name = 'muefs-webmcp-verify'

docker rm -f $name 2>$null | Out-Null
docker run -d --name $name -p "${port}:8000" -e DEMO_MODE_SECRET=local-verify -e ALLOW_DEMO_MODE=true $tag | Out-Null

try {
  $healthy = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 2
    try {
      $h = (Invoke-WebRequest -Uri "http://localhost:$port/health" -UseBasicParsing -TimeoutSec 3).Content
      if ($h -match 'healthy') { $healthy = $true; break }
    } catch {}
  }
  if (-not $healthy) { throw "Container not healthy on :$port" }

  Push-Location (Join-Path $PSScriptRoot '..\frontend')
  try {
    npm run smoke:webmcp -- "http://localhost:$port"
    if ($LASTEXITCODE -ne 0) { throw 'Agent Hub browser checks failed' }
  } finally {
    Pop-Location
  }
  Write-Host "PASS $tag serves a working Agent Hub"
} finally {
  docker rm -f $name 2>$null | Out-Null
}
