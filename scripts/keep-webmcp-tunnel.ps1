# Keep the WebMCP Docker container + Cloudflare quick tunnel up for judges.
# Usage: powershell -File scripts/keep-webmcp-tunnel.ps1
# Leaves a workers.dev / webmcp.tomcedoz.com front door healthy while this PC is awake.
$ErrorActionPreference = 'Stop'
$cloudflared = Join-Path $env:TEMP 'cloudflared.exe'
if (-not (Test-Path $cloudflared)) {
  Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $cloudflared -UseBasicParsing
}

function Ensure-Container {
  $running = docker ps --filter name=muefs-webmcp-tunnel --format '{{.Names}}'
  if (-not $running) {
    Write-Host 'Starting muefs-webmcp-tunnel on :8010'
    docker rm -f muefs-webmcp-tunnel 2>$null | Out-Null
    docker run -d --name muefs-webmcp-tunnel -p 8010:8000 `
      -e ALLOW_DEMO_MODE=true -e DEMO_ISOLATED_SESSIONS=true -e DEMO_MODE_SECRET=local-verify `
      -e ALLOWED_ORIGINS=https://webmcp.tomcedoz.com,https://muefs-webmcp-live.tom-72b.workers.dev,https://demo.tomcedoz.com `
      muefs-demo:webmcp | Out-Null
  }
  $healthy = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
      if ((Invoke-WebRequest http://127.0.0.1:8010/health -UseBasicParsing -TimeoutSec 2).Content -match 'healthy') {
        $healthy = $true; break
      }
    } catch {}
  }
  if (-not $healthy) { throw 'Container failed health check on :8010' }
}

function Ensure-Tunnel {
  $cf = Get-CimInstance Win32_Process -Filter "name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '8010' }
  if ($cf) { return }
  Write-Host 'Starting cloudflared quick tunnel -> :8010'
  Write-Host 'NOTE: If the trycloudflare hostname changes, update ORIGIN in cf-webmcp/src/proxy.js and redeploy.'
  Start-Process -FilePath $cloudflared -ArgumentList @('tunnel','--url','http://127.0.0.1:8010') -WindowStyle Minimized
  Start-Sleep -Seconds 8
}

Write-Host 'WebMCP keep-alive — Ctrl+C to stop. Front door: https://webmcp.tomcedoz.com/agent'
while ($true) {
  try {
    Ensure-Container
    Ensure-Tunnel
    $ok = $false
    try {
      $r = Invoke-WebRequest https://muefs-webmcp-live.tom-72b.workers.dev/health -UseBasicParsing -TimeoutSec 20
      if ($r.Content -match 'healthy') { $ok = $true }
    } catch {}
    $ts = Get-Date -Format 'HH:mm:ss'
    if ($ok) { Write-Host "$ts front-door OK" } else { Write-Host "$ts front-door FAIL — check tunnel hostname vs proxy.js ORIGIN" }
  } catch {
    Write-Host "$(Get-Date -Format HH:mm:ss) $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 60
}
