# Filing wizard

The filing wizard lets an attorney or SRL start an e-filing: pick a court, choose new vs existing case, then continue through documents. A filing in an existing case can be pre-filled from a case docket via File in this case.

## Sub-features

- `wizard-open` opens `New filing` from dashboard `Start a filing` and sidebar `New filing`.
- `wizard-court` filters courts and selects `3rd Circuit Court`.
- `wizard-existing` chooses `File in an existing case`.
- `wizard-from-docket` opens the wizard pre-filled via `File in this case` on a case the filer can see.
- `wizard-draft` shows the recovered-edits banner after a reload mid-wizard.

## How to get to it (user POV)

- Sign in as attorney or SRL, choose `Start a filing` on the dashboard.
- Choose sidebar `New filing` (`/filing/new`).
- On a case detail page, choose `File in this case` (hidden for public/anonymous).
- Clerk or administrator visiting `/filing/new` is redirected home.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- Signed in as attorney: `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=attorney`.
- `control-muefs doctor` is clean.
- Dismiss an unexpected draft banner with `Start fresh` before a fresh proof.

- **Open wizard.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /filing/new` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Select a court"`. Heading `New filing` (or `File in an existing case` / plain-language variants) is visible with labelled `Search courts`.
- **Pick court.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Search courts" --value "3rd Circuit"`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "3rd Circuit Court" --exact`. The court card is selected.
- **Proof.** After court select, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser screenshot --path artifacts/filing-wizard/court.png` and `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser snapshot --path artifacts/filing-wizard/court.aria.txt`. They show MUEFS and `3rd Circuit Court`.
- **Continue.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Continue"` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Existing case or new case?"`.
- **Existing case.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "File in an existing case"` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --label "Case number or party name"`.
- **From docket.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /cases/search?party=Smith`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role link --name "000001-CZ"`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role link --name "File in this case"`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "File in an existing case"`. The URL has `case_id`.

Do not complete payment or submit as the default proof. Those hit demo payment stubs and write `demo.db`.

## Gotchas

- Draft recovery (`Continue editing` / `Start fresh`, `Use saved details` for a saved filing, or `Start a separate filing` after an uncertain save) intercepts `/filing/new` while this tab's sessionStorage holds a `muefs_filing_draft:v2:` entry. Choose `Start fresh` for a clean court-step proof.
- Each court card's select button is named with the court name. The favorite star is a separate button named `Add <court name> to favorites` or `Remove <court name> from favorites`. Use `--exact`: without it, `3rd Circuit Court` also matches `23rd Circuit Court` and the stars.
- `Continue` shows an error until a court is selected.
- Public role cannot open the wizard; they get bounced to `/`.
- Plain-language guidance changes the H1 (`Start a new court filing`, `File papers in an existing case`) and the step labels (`Your court`, `Your case`). Assert one of the known headings, not a single string.
- The SRL role turns plain-language guidance on, and the choice stays in `localStorage` after `Switch role`. An attorney in the same browser then sees the plain headings until the box is cleared.
