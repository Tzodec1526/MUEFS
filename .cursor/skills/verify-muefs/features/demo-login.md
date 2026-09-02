# Demo login

Demo login lets a visitor pick Attorney, Court Clerk, Self-Represented Litigant, or Public and land on the matching home, then switch role without a password.

## Sub-features

- `login-open` shows the four role cards on `/login`.
- `login-attorney` signs in as attorney and shows the filer dashboard (`Start Filing`).
- `login-clerk` signs in as clerk and shows `Open Queue`.
- `login-srl` signs in as self-represented and shows the filer dashboard.
- `login-public` uses `Browse records` / `role=public` and lands on case search.
- `login-switch` returns to `/login` via `Switch Role`.

## How to get to it (user POV)

- Open `/login` (unauthenticated routes redirect here except `/cases/*` and `/agent`).
- Open `/login?role=attorney` (or `clerk`, `srl`, `public`) — applies the role and navigates.
- Choose `Sign In` on the Attorney, Court Clerk, or SRL card; choose `Browse records` on Public docket.
- Choose `Switch Role` in the header when already signed in.
- Demo banner `Roles` link goes to `/login`.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `control-muefs doctor` reports a healthy API and portal.
- No assumption about a prior `demo_role`.

- **Open login.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login`. The heading `Michigan Unified E-Filing System` is visible and four role cards include `Attorney`, `Court Clerk`, `Self-Represented Litigant`, and `Public docket`.
- **Attorney via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=attorney`. The dashboard heading `Your filings` appears and a `Start Filing` link is visible. The header badge reads `Attorney`.
- **Clerk via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=clerk`. An `Open Queue` link is visible and the badge reads `Court Clerk`.
- **Public via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=public`. The case-search heading `Statewide case search` is visible.
- **Switch role.** From a signed-in page, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Switch Role"`. `/login` returns with the four cards.
- **Proof.** After attorney sign-in, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser snapshot --path artifacts/demo-login/attorney.aria.txt` and `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser screenshot --path artifacts/demo-login/attorney.png`. Both identify MUEFS and `Your filings` / `Attorney`.

## Gotchas

- Three cards use a button named `Sign In`. Do not `click --role button --name "Sign In"` without scoping; use `/login?role=…` or the Public `Browse records` button.
- `/cases/search` and `/agent` are reachable without a role. That is not a failed login.
- Clerk also stores `demo_court_id=3` / `3rd Circuit Court - Wayne County`. Switching role clears those keys.
- Production Keycloak (`Sign in with Keycloak (PKCE)`) is not part of the demo proof.
