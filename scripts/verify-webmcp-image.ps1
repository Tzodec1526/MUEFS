# Verify the production demo image includes WebMCP Agent Hub (no Render deploy).
# Uses :8011 by default so it does not clash with a long-running tunnel on :8010.
$ErrorActionPreference = 'Stop'
$tag = if ($args[0]) { $args[0] } else { 'muefs-demo:webmcp' }
$port = if ($env:MUEFS_VERIFY_PORT) { [int]$env:MUEFS_VERIFY_PORT } else { 8011 }
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
  $need = @('attorney_motion_workflow', 'get_agent_session', 'get_agent_activity', 'agent-hub', 'Declarative WebMCP')
  foreach ($n in $need) {
    if (-not $body.Contains($n)) { throw "Missing marker in bundle: $n" }
  }

  $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
  $search = (Invoke-WebRequest -Uri "http://localhost:$port/api/v1/cases/search?party_name=Smith&page=1" -UseBasicParsing -WebSession $session).Content | ConvertFrom-Json
  if (-not $search.cases -or $search.cases.Count -lt 1) { throw 'Smith search returned no cases' }
  $c = $search.cases[0]
  $req = (Invoke-WebRequest -Uri "http://localhost:$port/api/v1/courts/$($c.court_id)/case-types/$($c.case_type_id)/requirements?filing_type=subsequent" -UseBasicParsing -WebSession $session).Content | ConvertFrom-Json
  if ($req.Count -lt 1) {
    throw "Smith case type $($c.case_type_id) has no filing requirements (expected CIV-GEN)"
  }

  Write-Host "PASS $tag serves WebMCP hub (bundle $js, Smith req=$($req.Count))"
} finally {
  cmd /c "docker rm -f $name >nul 2>&1"
}
