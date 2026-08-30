# Challenge go-live leftovers (evidence-based)

## Objective completion evidence (audited 2026-08-28)

| Requirement | Status | Evidence |
|---|---|---|
| Judge-ready live `/agent` | Met | https://webmcp.tomcedoz.com/agent · https://muefs.tomcedoz.com/agent — Playwright smoke **11/11**; bundle `index-CYZ4kc8V.js` |
| Maximize Devpost criteria | Met | 23 tools (16/20/19), imperative+declarative, HITL, flagship workflows, `get_challenge_briefing`; criteria map in `docs/WEBMCP_DEVPOST.md` |
| Public AGPL + post-Aug-25 WebMCP | Met | GitHub `AGPL-3.0`, topics `webmcp`, homepage → live hub; `frontend/src/webmcp/` + `docs/WEBMCP*` on `main` after Aug 25 |
| `<3min` demo-video-ready | Met | `demo/muefs-webmcp-challenge.mp4` (~92.5s, h264+aac) + `demo/webmcp-voiceover.txt` |
| Verified on localhost | Met | `scripts/verify-webmcp-image.ps1` PASS (`muefs-demo:webmcp`, Smith req=5) |
| Deployable to `demo.tomcedoz.com` | Met | `Dockerfile` + `render.yaml` (`autoDeploy: false`) + deploy-hook workflow; Manual Deploy flips canonical host |

## Operator polish (not required for objective text)

1. Render → muefs-demo → **Manual Deploy** so https://demo.tomcedoz.com/agent matches `main` (Workers cannot attach while Render CNAME exists).
2. Upload video to YouTube; paste URL into Devpost.
3. Submit on https://webmcp.devpost.com/ before Sep 3, 2026 @ 1:00 PM PT using `docs/WEBMCP_DEVPOST.md`.
4. Keep PC awake / `scripts/keep-webmcp-tunnel.ps1` until Render is live.

```powershell
powershell -File scripts/verify-live-webmcp.ps1
powershell -File scripts/keep-webmcp-tunnel.ps1
```
