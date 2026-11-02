# Case search

Case search lets anyone look up non-sealed Michigan demo cases by party name or case number, open a docket, and tell a miss from an empty recent list.

## Sub-features

- `search-open` opens search from the sidebar, the public dashboard, and `/cases/search`.
- `search-party` returns Smith matches including `Johnson v. Smith Industries LLC`.
- `search-empty` shows the no-cases copy for a nonsense query.
- `search-open-case` opens a result by case-number link.
- `search-public` works with no demo role (anonymous or `public`).
- `search-api` returns the same hits from `GET /api/v1/cases/search`.

## How to get to it (user POV)

- Open `/cases/search` (no account).
- Choose `Case search` in the sidebar.
- On the public dashboard (`/` with the `public` role), fill the form and choose `Search cases`.
- From login as public, land on search automatically.
- Share a URL with `?party=Smith` or `?case=…`.

## Driving it with control-muefs

Preconditions:

- MUEFS is healthy at `http://127.0.0.1:3000`.
- `backend/demo.db` is seeded (Smith party present).
- `control-muefs doctor` reports the expected URL and `muefs-api`.

- **Open search.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /cases/search` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Case search"`. Labelled fields `Case number` and `Party name` are visible.
- **Party match.** Fill and submit. Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Party name" --value Smith`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Search"`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Results"`. The table includes `Johnson v. Smith Industries LLC` (or another seeded Smith title). The URL contains `party=Smith`.
- **Proof.** After the Smith search, run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser snapshot --path artifacts/case-search/results.aria.txt` and `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser screenshot --path artifacts/case-search/results.png`. Artifacts show MUEFS identity, query Smith, and at least one result row.
- **Open docket.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role link --name "000001-CZ"` then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Johnson v. Smith Industries LLC"` (the link text is the visible case number; the seed prefixes the current year). Public viewers do not see `File in this case`.
- **Empty state.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser goto /cases/search`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser fill --label "Party name" --value zzzxnotacase`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser click --role button --name "Search"`, then `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs browser wait --role heading --name "Results (0)"`. Copy `No cases found. Check the number or name. Partial matches work.` is visible.
- **API second view.** Run `node .cursor/skills/verify-muefs/helpers/control-muefs.mjs api get /api/v1/cases/search?party_name=Smith --path artifacts/case-search/search.json`. HTTP 200; JSON `cases` is non-empty and a title contains `Smith`.

## Gotchas

- The page loads recent public filings before you search. `Results (N)` vs `Recent public filings` is the difference between a submitted search and the default list.
- `--name "Search"` matches by substring. On `/cases/search` the only match is the form's submit button; the sidebar's `Case search` is a link, not a button.
- Sealed cases are excluded from this index. A 403 on case detail is a restricted docket, not a search bug.
- Attorney/SRL see favorite stars; public/anonymous do not. Do not treat a missing star column as a failed search.
- Opening a case changes the page. Re-goto `/cases/search?party=Smith` before another query proof.
