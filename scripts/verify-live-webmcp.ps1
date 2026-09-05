# Verify the live Agent Hub through its rendered search and docket flow.
$ErrorActionPreference = 'Stop'
$url = if ($args[0]) { $args[0] } else { 'https://demo.tomcedoz.com' }
Push-Location (Join-Path $PSScriptRoot '..\frontend')
try {
  npm run smoke:webmcp -- $url
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
