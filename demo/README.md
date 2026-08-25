# MUEFS demo walkthrough

`muefs-walkthrough-60s.mp4` — attorney-role walkthrough (~60 seconds):

1. Login screen → Attorney sign-in  
2. Dashboard with platform stats  
3. Case search (`party=Smith`)  
4. Case detail → **File with Court**  
5. Pre-filled filing wizard  

## Regenerate

Requires local dev servers (`npm run dev` + backend on port 8000) and [browser-use](https://github.com/browser-use/browser-harness):

```powershell
.\scripts\record-walkthrough.ps1
```

Raw frames are saved under `%USERPROFILE%\.config\browser-harness\agent-workspace\recordings\`.
