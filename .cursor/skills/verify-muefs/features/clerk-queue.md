# Clerk review queue

The review queue lists pending filings for the demo court (3rd Circuit / Wayne), lets a clerk open one, and offers Accept, Return for correction, and Reject.

## Sub-features

- `queue-open` opens `/clerk/queue` after clerk sign-in (`Open review queue` on the clerk dashboard).
- `queue-list` shows `Review queue` with a matching-filings count and rows or `No filings match these filters in this court.`
- `queue-open-filing` chooses `Review filing #<id>` and shows `Filing #<id>` with `Review actions`.
- `queue-refresh` reloads via the filter form's `Refresh` button.

## How to get to it (user POV)

- Sign in as Court clerk, choose `Open review queue`.
- Sidebar `Review queue`.
- Direct `/clerk/queue` while `demo_role=clerk`.
- Accounts with no court assignment see `Court assignment needed` on that path.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /login?role=clerk`.
- `control-muefs doctor` is clean.
- Seeded queue may be empty; empty is a valid end state.

- **Open queue.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /clerk/queue` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Review queue"`. The `Working court` select shows `3rd Circuit Court`. Filter control `Filter` is present.
- **Refresh.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Refresh" --exact` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Review queue"`. The page still shows the queue heading (the button may briefly read `Loading...`).
- **Open a filing (if rows exist).** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Review filing #"` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Filing #"`. The panel shows `Review actions` with `Accept`, `Return for correction`, and `Reject`.
- **Proof.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser snapshot --path artifacts/clerk-queue/queue.aria.txt` and `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser screenshot --path artifacts/clerk-queue/queue.png`. They show MUEFS and `Review queue`. If the queue is empty, the empty-row copy is the proof. Do not invent a filing.

Default proof **does not** click Accept, Return, or Reject. Those mutate `backend/demo.db` and Reject shows a browser confirm.

## Gotchas

- Reject is final and pops `window.confirm`. Return requires a reason (`Reason (required to reject or return)` / `Review reason`).
- `--name "Refresh"` without `--exact` matches `Refresh assignments` first, which reloads the court list instead of the queue.
- Clicking a row also opens it, but the `Review filing #<id>` button is the keyboard path and the stable handle.
- Auto-refresh every 30s while no filing is open. Do not treat a count change mid-proof as a flake without checking the API.
- Attaching to a user's demo and accepting filings is how you corrupt their queue. Prefer a launch this run owns.
- `Select all filings` is a checkbox name, not a submit action.
