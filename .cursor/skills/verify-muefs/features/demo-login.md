# Demo login

Demo login lets a visitor pick Attorney, Court clerk, Self-represented litigant, System administrator, or Public docket and land on the matching home, then switch role without a password.

## Sub-features

- `login-open` shows the five role choices on `/login`.
- `login-attorney` signs in as attorney and shows the filer dashboard (`Start a filing`).
- `login-clerk` signs in as clerk and shows `Open review queue`.
- `login-srl` signs in as self-represented and shows the filer dashboard.
- `login-admin` signs in as administrator and shows `People and court access`.
- `login-public` uses `Browse records` / `role=public` and lands on case search.
- `login-switch` returns to `/login` via `Switch role`.

## How to get to it (user POV)

- Open `/login`. Signed-out visitors are redirected here from every route except the public set: `/about`, `/cases/search`, `/cases/{id}` and `/courts/*`.
- Open `/login?role=attorney` (or `clerk`, `srl`, `public`, `admin`). It applies the role and navigates.
- Choose `Sign in` on the Attorney, Court clerk, Self-represented litigant or System administrator row (accessible names `Sign in as Attorney` and so on); choose `Browse records` on Public docket.
- Choose `Switch role` in the header when already signed in.
- Demo banner `Roles` link goes to `/login`.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `control-muefs doctor` reports a healthy API and portal.
- No assumption about a prior `demo_role`.

- **Open login.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Sign in"`. The page names `Michigan Unified E-Filing System` above the heading and lists `Attorney`, `Court clerk`, `Self-represented litigant`, `Public docket`, and `System administrator`.
- **Attorney via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=attorney` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role link --name "Start a filing"`. The dashboard heading `Your filings` appears and the header badge reads `Attorney`.
- **Proof.** After attorney sign-in, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser snapshot --path artifacts/demo-login/attorney.aria.txt` and `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser screenshot --path artifacts/demo-login/attorney.png`. Both identify MUEFS and `Your filings` / `Attorney`.
- **Clerk via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=clerk` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role link --name "Open review queue"`. The heading is the court name, `3rd Circuit Court`, and the badge reads `Court clerk`.
- **Administrator via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=admin` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "People and court access"`.
- **Public via URL.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=public` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Case search"`.
- **Switch role.** From a signed-in page, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Switch role"` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role button --name "Browse records"`. `/login` returns with the five role choices.

## Gotchas

- Four rows show a button labelled `Sign in`; their accessible names differ (`Sign in as Attorney`). A partial `--name "Sign in"` matches all four, so use the full name with `--exact`, `/login?role=…`, or the Public `Browse records` button.
- `/cases/search` and `/about` are reachable without a role. That is not a failed login.
- Clerk also stores `demo_court_id=3` (the 3rd Circuit Court). Switching role clears it.
- Production sign-in (`Sign in with your court account`) is not part of the demo proof.
