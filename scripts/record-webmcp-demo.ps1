# Silent B-roll for WebMCP challenge video (add voiceover from demo/webmcp-voiceover.txt).
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$recordingName = 'muefs-webmcp-challenge'
$recordingDir = Join-Path $env:USERPROFILE ".config\browser-harness\agent-workspace\recordings\$recordingName"
$outMp4 = Join-Path $repoRoot 'demo\muefs-webmcp-challenge-broll.mp4'

New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot 'demo') | Out-Null
if (Test-Path $recordingDir) { Remove-Item -Recurse -Force $recordingDir }

$py = @'
import time
start_recording("muefs-webmcp-challenge", title="MUEFS WebMCP Challenge B-roll")
new_tab("http://localhost:3000/agent")
wait_for_load()
time.sleep(3)
js("(() => { const list=[...document.querySelectorAll('button')]; const b=list.find(el=>/Attorney/i.test(el.textContent||'')); if(b){b.click(); return 'attorney'} return 'nofind' })()")
time.sleep(6)
js("(() => { const list=[...document.querySelectorAll('button')]; const b=list.find(el=>/Open result path/i.test(el.textContent||'')); if(b){b.click(); return 'wizard'} return 'nowizard' })()")
time.sleep(4)
new_tab("http://localhost:3000/agent")
wait_for_load()
time.sleep(2)
js("(() => { const list=[...document.querySelectorAll('button')]; const b=list.find(el=>/Clerk/i.test(el.textContent||'')); if(b){b.click(); return 'clerk'} return 'nofind' })()")
time.sleep(5)
new_tab("http://localhost:3000/cases/search?party=Smith")
wait_for_load()
time.sleep(3)
stop_recording()
'@

$py | browser-use | Out-Host

if (-not (Test-Path $recordingDir)) {
  throw "Recording folder not found: $recordingDir"
}

$frames = (Get-ChildItem $recordingDir -Filter '*.jpg').Count
if ($frames -lt 3) { throw "Expected frames in $recordingDir, found $frames" }

ffmpeg -y -framerate 1/5 -start_number 1 -i "$recordingDir\%04d.jpg" -c:v libx264 -pix_fmt yuv420p `
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" `
  $outMp4

Write-Host "Wrote $outMp4 ($frames frames). Narrate with demo/webmcp-voiceover.txt. Audio is required for Devpost."
