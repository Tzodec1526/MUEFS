# Verify the production demo image includes WebMCP Agent Hub (no Render deploy).
$ErrorActionPreference = 'Stop'
$tag = if ($args[0]) { $args[0] } else { 'muefs-demo:webmcp' }
$port = 8010
$name = 'muefs-webmcp-verify'

cmd /c "docker rm -f $name >nul 2>&1"
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

  $html = (Invoke-WebRequest -Uri "http://localhost:$port/agent" -UseBasicParsing).Content
  if ($html -notmatch 'assets/([^"]+\.js)') { throw 'SPA bundle not found on /agent' }
  $js = $Matches[1]
  $body = (Invoke-WebRequest -Uri "http://localhost:$port/assets/$js" -UseBasicParsing).Content
  $need = @('attorney_motion_workflow', 'get_agent_session', 'agent-hub')
  foreach ($n in $need) {
    if (-not $body.Contains($n)) { throw "Missing marker in bundle: $n" }
  }
  Write-Host "PASS $tag serves WebMCP hub (bundle $js)"
} finally {
  cmd /c "docker rm -f $name >nul 2>&1"
}
