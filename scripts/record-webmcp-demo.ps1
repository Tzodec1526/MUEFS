# Record a ~90s WebMCP challenge demo (agent + human UI)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$recordingName = 'muefs-webmcp-challenge'
$recordingDir = Join-Path $env:USERPROFILE ".config\browser-harness\agent-workspace\recordings\$recordingName"
$outMp4 = Join-Path $repoRoot 'demo\muefs-webmcp-challenge.mp4'

New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot 'demo') | Out-Null

$py = @'
import time
start_recording("muefs-webmcp-challenge", title="MUEFS WebMCP Challenge Demo")
new_tab("http://localhost:3000/agent")
wait_for_load()
time.sleep(3)
new_tab("http://localhost:3000/login?role=attorney")
wait_for_load()
time.sleep(3)
new_tab("http://localhost:3000/cases/search?party=Smith")
wait_for_load()
time.sleep(3)
js("window.scrollTo(0,300)")
time.sleep(2)
new_tab("http://localhost:3000/agent")
wait_for_load()
time.sleep(3)
stop_recording()
'@

$py | browser-use | Out-Host

ffmpeg -y -framerate 1/5 -start_number 1 -i "$recordingDir\%04d.jpg" -frames:v 18 -c:v libx264 -pix_fmt yuv420p `
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" `
  $outMp4

Write-Host "Wrote $outMp4 (~90s)"
