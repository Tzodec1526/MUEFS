# Challenge go-live leftovers (evidence-based)

## Done on main (verified)

- Public AGPL-3.0 badge on GitHub
- Post-Aug-25 WebMCP commits on `main` (`frontend/src/webmcp/`, `/agent`, docs)
- Localhost `/agent` with flagship attorney/clerk/SRL runners + activity feed
- Docker image `muefs-demo:webmcp` builds and `scripts/verify-webmcp-image.ps1` PASS
- `render.yaml` `autoDeploy: false` (no surprise prod deploys)
- Silent B-roll: `demo/muefs-webmcp-challenge-broll.mp4` + VO script `demo/webmcp-voiceover.txt`
- Draft video **with audio** (~95s TTS): `demo/muefs-webmcp-challenge.mp4` (prefer re-record with ChatGPT before Devpost)
- Live front door (tunnel-backed): **https://webmcp.tomcedoz.com/agent** (+ workers.dev)
- Devpost paste: `docs/WEBMCP_DEVPOST.md`
- Playwright hub smoke: `frontend/scripts/smoke-webmcp-ui.mjs` (11/11 against workers.dev)

## Interim public URL (this machine)

While `demo.tomcedoz.com` awaits Manual Deploy:

- Container: `muefs-webmcp-tunnel` on `:8010` (`muefs-demo:webmcp`)
- Quick tunnel: `cloudflared tunnel --url http://127.0.0.1:8010`
- Stable front door: **https://webmcp.tomcedoz.com/agent** (Workers Custom Domain → tunnel)
- Also: https://muefs-webmcp-live.tom-72b.workers.dev/agent
- Keep-alive: `powershell -File scripts/keep-webmcp-tunnel.ps1`

Dies when the tunnel process or PC sleeps. Prefer Render Manual Deploy for Devpost freeze.

**Blocked without your click:** DNS OAuth cannot edit `demo.tomcedoz.com` (Render CNAME / orange-to-orange). Worker routes on that host do not override Render. `RENDER_DEPLOY_HOOK_URL` GitHub secret is not set.

After Manual Deploy, verify:

```powershell
powershell -File scripts/verify-live-webmcp.ps1
```

## Not done (blocks goal complete)

1. **Manual Render deploy** of latest `main` so https://demo.tomcedoz.com/agent serves the hub
2. Prefer a live ChatGPT capture over the TTS draft before YouTube upload
3. **Devpost submission** — paste from `docs/WEBMCP_DEVPOST.md` before Sep 3, 2026 @ 1:00 PM PT

## Your next three clicks

1. Render → muefs-demo → Manual Deploy (or `gh secret set RENDER_DEPLOY_HOOK_URL` then Actions → Deploy demo)
2. Upload `demo/muefs-webmcp-challenge.mp4` to YouTube (or re-record with ChatGPT + `demo/webmcp-voiceover.txt`)
3. Submit on Devpost using `docs/WEBMCP_DEVPOST.md`
