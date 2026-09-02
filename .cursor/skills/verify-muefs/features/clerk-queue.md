# Clerk review queue

The clerk review queue lists pending filings for the demo court (3rd Circuit / Wayne), lets a clerk open one, and offers Accept, Return for Correction, and Reject.

## Sub-features

- `queue-open` opens `/clerk/queue` after clerk sign-in (`Open Queue` on the clerk dashboard).
- `queue-list` shows `Clerk Review Queue` with a Pending count and rows or `No pending filings for this court`.
- `queue-open-filing` selects a row and shows `Filing #<id>` with Review Actions.
- `queue-refresh` reloads via the Filter form `Refresh` button.

## How to get to it (user POV)

- Sign in as Court Clerk, choose `Open Queue`.
- Header or sidebar `Review Queue`.
- Direct `/clerk/queue` while `demo_role=clerk`.
- Non-clerks hitting that path are redirected home.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `browser goto /login?role=clerk`.
- `control-muefs doctor` is clean.
- Seeded queue may be empty; empty is a valid end state.

- **Open queue.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /clerk/queue`. Heading `Clerk Review Queue` is visible. Court label is `3rd Circuit Court - Wayne County`. Filter control `Filter` is present.
- **Refresh.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Refresh"`. The page still shows the queue heading (loading label may briefly read `Refreshing...`).
- **Open a filing (if rows exist).** Click a table row (case title cell). Panel heading `Filing #` appears with `Accept`, `Return for Correction`, and `Reject`.
- **Proof.** Snapshot and screenshot to `artifacts/clerk-queue/queue.aria.txt` and `artifacts/clerk-queue/queue.png`. They show MUEFS and `Clerk Review Queue`. If the queue is empty, the empty-row copy is the proof — do not invent a filing.

Default proof **does not** click Accept, Return, or Reject. Those mutate `backend/demo.db` and Reject shows a browser confirm.

## Gotchas

- Reject is final and pops `window.confirm`. Return requires a reason (`Reason (required for reject/return)` / `Review reason`).
- Auto-refresh every 30s while no filing is open. Do not treat a count change mid-proof as a flake without checking the API.
- Attaching to a user's demo and accepting filings is how you corrupt their queue. Prefer a launch this run owns.
- `Select all filings` is a checkbox name, not a submit action.
