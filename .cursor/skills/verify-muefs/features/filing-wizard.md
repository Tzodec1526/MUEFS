# Filing wizard

The filing wizard lets an attorney or SRL start an e-filing: pick a court, choose new vs existing case, then continue through documents. Motion filing can be pre-filled from a case docket via File with Court.

## Sub-features

- `wizard-open` opens `New E-Filing` from dashboard `Start Filing` and header `New Filing`.
- `wizard-court` filters courts and selects `3rd Circuit Court`.
- `wizard-existing` chooses `File into an existing case`.
- `wizard-from-docket` opens the wizard pre-filled via `File with Court` on a case the filer can see.
- `wizard-draft` shows the unsaved-draft banner after a reload mid-wizard.

## How to get to it (user POV)

- Sign in as attorney or SRL, choose `Start Filing` on the dashboard.
- Choose header or sidebar `New Filing` (`/filing/new`).
- On a case detail page, choose `File with Court` (hidden for public/anonymous).
- Clerk visiting `/filing/new` is redirected home.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- Signed in as attorney: `browser goto /login?role=attorney`.
- `control-muefs doctor` is clean.
- Discard an unexpected draft banner with `Discard Draft` before a fresh proof.

- **Open wizard.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /filing/new`. Heading `New E-Filing` (or `File a Motion` / plain-language variants) is visible with `Select Court` and labelled `Search courts`.
- **Pick court.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Search courts" --value "3rd Circuit"` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "3rd Circuit Court"`. The court card is selected. Click `Continue`. Heading `Existing case or new case?` appears.
- **From docket.** Search Smith, open a case, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role link --name "File with Court"`. Wizard opens with motion/case context (URL has `case_id`).
- **Proof.** After court select, run snapshot and screenshot to `artifacts/filing-wizard/court.png` and `artifacts/filing-wizard/court.aria.txt`. They show MUEFS and `3rd Circuit Court`.

Do not complete payment or submit as the default proof. Those hit demo payment stubs and write `demo.db`.

## Gotchas

- Draft recovery (`Continue Draft` / `Discard Draft`) intercepts a second `/filing/new` if localStorage still has `muefs_filing_draft`. Discard for a clean court-step proof.
- Court cards are `role=button` named with the court name. Favorite stars on the card are separate buttons (`Add court to favorites`).
- `Continue` is disabled or a no-op until a court is selected.
- Public role cannot open the wizard; they get bounced to `/`.
- Plain-language toggle changes the H2 copy (`Start a new court filing`). Assert one of the known headings, not a single string.
