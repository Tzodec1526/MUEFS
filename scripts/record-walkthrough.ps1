# Record a ~60s MUEFS attorney walkthrough and encode demo/muefs-walkthrough-60s.mp4
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$recordingName = 'muefs-walkthrough-60s'
$recordingDir = Join-Path $env:USERPROFILE ".config\browser-harness\agent-workspace\recordings\$recordingName"
$outMp4 = Join-Path $repoRoot 'demo\muefs-walkthrough-60s.mp4'

New-Item -ItemType Directory -Force -Path (Join-Path $repoRoot 'demo') | Out-Null

$py = @'
import time
start_recording("muefs-walkthrough-60s", title="MUEFS Attorney Walkthrough")
new_tab("http://localhost:3000/login")
wait_for_load()
time.sleep(2)
js("const cards=[...document.querySelectorAll('.login-card')]; const att=cards.find(c=>c.textContent.includes('Attorney')); const btn=att&&att.querySelector('button'); if(btn){btn.click();'ok'} else 'fail'")
time.sleep(4)
new_tab("http://localhost:3000/cases/search?party=Smith")
wait_for_load()
time.sleep(4)
js("const link=document.querySelector('table tbody tr a'); if(link){link.click();'case'} else 'nocase'")
time.sleep(4)
js("const a=[...document.querySelectorAll('a')].find(el=>/file with court/i.test(el.textContent||'')); if(a){a.click();'file'} else 'nofile'")
time.sleep(5)
stop_recording()
'@

$py | browser-use | Out-Host

if (-not (Test-Path $recordingDir)) {
  throw "Recording folder not found: $recordingDir"
}

ffmpeg -y -framerate 1/6 -start_number 1 -i "$recordingDir\%04d.jpg" -frames:v 10 -c:v libx264 -pix_fmt yuv420p `
  -vf "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2" `
  $outMp4

Write-Host "Wrote $outMp4"
