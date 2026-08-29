# Challenge go-live leftovers (evidence-based)

## Objective completion evidence (audited)

| Requirement | Evidence |
|---|---|
| Judge-ready live `/agent` | https://webmcp.tomcedoz.com/agent · https://muefs.tomcedoz.com/agent — Playwright smoke **11/11** |
| Public AGPL + post-Aug-25 WebMCP | GitHub `AGPL-3.0`, topics `webmcp`/`openai-challenge`; commits on `main` after Aug 25 under `frontend/src/webmcp/` + `docs/WEBMCP*` |
| `<3min` demo-video-ready | `demo/muefs-webmcp-challenge.mp4` (~93s, h264+aac) + `demo/webmcp-voiceover.txt` |
| Verified on localhost | `scripts/verify-webmcp-image.ps1` PASS (`muefs-demo:webmcp`, Smith req=5) |
| Deployable to `demo.tomcedoz.com` | `Dockerfile` + `render.yaml` (`autoDeploy: false`) + Manual Deploy / deploy-hook Action path |

## Done on main

- 23-tool role-aware WebMCP catalog (16 / 20 / 19) + `get_challenge_briefing`
- `/agent` hub: activity feed, declarative search, flagship runners, judge prompts
- Live front doors (tunnel-backed until Render Manual Deploy): **webmcp** · **muefs** · workers.dev
- Devpost paste: `docs/WEBMCP_DEVPOST.md`

## Operator (post-objective / submission polish)

1. Render → muefs-demo → **Manual Deploy** (or `gh secret set RENDER_DEPLOY_HOOK_URL` + Actions) so canonical https://demo.tomcedoz.com/agent matches `main` — DNS still points at Render; Workers custom domain cannot attach while that CNAME exists.
2. Prefer a live agent capture over TTS; upload YouTube; paste URL into Devpost.
3. Submit on https://webmcp.devpost.com/ before Sep 3, 2026 @ 1:00 PM PT using `docs/WEBMCP_DEVPOST.md`.
4. Keep PC awake / `scripts/keep-webmcp-tunnel.ps1` until Render is live.

```powershell
powershell -File scripts/verify-live-webmcp.ps1
powershell -File scripts/keep-webmcp-tunnel.ps1
```
