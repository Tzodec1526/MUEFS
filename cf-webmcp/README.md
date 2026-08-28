# Cloudflare Containers edge for a durable WebMCP Challenge live URL
# (backup while Render Manual Deploy is pending for demo.tomcedoz.com).

## Status

Scaffold is ready. `wrangler deploy` uploads the Worker, but pushing the
container image currently returns **401 Unauthorized** on
`/accounts/.../containers/me` — the Wrangler OAuth token needs Containers
scope. Re-auth once:

```powershell
cd cf-webmcp
npx wrangler logout
npx wrangler login
$env:CLOUDFLARE_ACCOUNT_ID='72b88976acc5bc6d8cae287f05bde80a'
npm run deploy
```

Then open `https://muefs-webmcp.<subdomain>.workers.dev/agent`.

## Local commands

```powershell
cd cf-webmcp
npm install
npm run deploy
```
