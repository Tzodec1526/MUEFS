# MUEFS verification map

This directory is the maintained source for verifying the user-facing behavior of the MUEFS demo filing portal. Read the index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch the demo at `http://127.0.0.1:3000` with API `http://127.0.0.1:8000` via `control-muefs launch`.
- Seed data is `backend/demo.db` (created by `run_demo.py`). Public search includes a Smith party (Johnson v. Smith Industries LLC).
- Run `control-muefs doctor` and require healthy `muefs-api` plus portal HTML that names Michigan Unified E-Filing System.
- Never drive an instance that was not started by this verification run unless `MUEFS_VERIFY_ATTACH=1` was set on purpose.
- Demo roles live in `localStorage`. Prefer `/login?role=attorney` (or `clerk`, `srl`, `public`) over clicking among three buttons all named `Sign In`.

## Driving conventions

- Start every recipe from the baseline state unless its preconditions say otherwise.
- Prefer ARIA roles, accessible names, and labelled inputs over CSS selectors or coordinates.
- Treat every command as literal. Keep quoted names and flags unchanged.
- Run browser actions through `control-muefs browser`.
- Run API second-views through `control-muefs api get`.
- Cleanup removes the owned process and browser profile. Do not remove proof artifacts.

## Proof and skip reporting

- Capture the user action and the resulting state, not only the final screen.
- UI proof includes an ARIA snapshot and a screenshot with the MUEFS header visible.
- Mutation proof includes a read-only second view of the stored value.
- Record the feature ID and entry point used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with control-muefs` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Demo login](./demo-login.md) covers role cards, query-param sign-in, Switch Role, and the public visitor path.
- [Case search](./case-search.md) covers public docket search, empty results, opening a case, and the API second view.
- [Filing wizard](./filing-wizard.md) covers attorney/SRL new filing, court pick, existing-case (File with Court), and draft recovery.
- [Clerk review queue](./clerk-queue.md) covers clerk sign-in, queue list, and opening a filing for review (no default accept/reject).
- [Agent Hub](./agent-hub.md) covers `/agent`, declarative Smith search, and the Attorney · Smith motion run.
