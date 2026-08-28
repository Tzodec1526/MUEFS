# Poll demo.tomcedoz.com until WebMCP Agent Hub is live (after Manual Deploy).
$ErrorActionPreference = 'Stop'
$url = if ($args[0]) { $args[0] } else { 'https://demo.tomcedoz.com' }
$deadline = (Get-Date).AddMinutes(15)
$markers = @('attorney_motion_workflow', 'get_agent_activity', 'Declarative WebMCP', 'agent-hub')

Write-Host "Polling $url for WebMCP markers until $deadline ..."
while ((Get-Date) -lt $deadline) {
  try {
    $html = (Invoke-WebRequest "$url/" -UseBasicParsing -TimeoutSec 20).Content
    if ($html -match 'assets/(index-[^"]+\.js)') {
      $js = $Matches[1]
      $body = (Invoke-WebRequest "$url/assets/$js" -UseBasicParsing -TimeoutSec 30).Content
      $missing = @($markers | Where-Object { -not $body.Contains($_) })
      if ($missing.Count -eq 0) {
        # Smith MCR sanity
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        $search = (Invoke-WebRequest "$url/api/v1/cases/search?party_name=Smith&page=1" -UseBasicParsing -WebSession $session -TimeoutSec 20).Content | ConvertFrom-Json
        $c = $search.cases[0]
        $req = (Invoke-WebRequest "$url/api/v1/courts/$($c.court_id)/case-types/$($c.case_type_id)/requirements?filing_type=subsequent" -UseBasicParsing -WebSession $session).Content | ConvertFrom-Json
        if ($req.Count -lt 1) { throw "Live Smith case has no requirements (type=$($c.case_type_id))" }
        Write-Host "PASS live WebMCP hub js=$js Smith req=$($req.Count)"
        exit 0
      }
      Write-Host "$(Get-Date -Format HH:mm:ss) js=$js missing=$($missing -join ',')"
    } else {
      Write-Host "$(Get-Date -Format HH:mm:ss) no SPA asset yet"
    }
  } catch {
    Write-Host "$(Get-Date -Format HH:mm:ss) $($_.Exception.Message)"
  }
  Start-Sleep -Seconds 20
}
Write-Host "TIMEOUT: $url still not serving WebMCP"
exit 1
