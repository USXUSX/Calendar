# Architecture decisions

## Confirmed

- Project root: `/Users/us/Tools`.
- Three layers: `Development`, `GoogleDrive`, and `LocalData`, each with a `Calendar` project folder.
- GitHub will be the canonical system for code, confirmed specifications, Issues, Pull Requests, and tests.
- GitHub repository: `USXUSX/Calendar`; local `origin` points to `git@github.com:USXUSX/Calendar.git`.
- The existing Calendar prototype will not be migrated during foundation setup.
- 2026-08-20, Issue #5: the first read-only UI uses browser-native HTML, CSS, and ES modules with no application framework or runtime dependencies. It is served locally as static files, reads only committed synthetic JSON, and exists to validate the display contract and information design before a production architecture is selected.
- 2026-08-22, Issue #27: real trip data is kept only under `/Users/us/Tools/LocalData/Calendar_Local/trips/<trip-id>/`. `current.json` is the adopted source of truth, `candidate.json` is an unadopted complete-JSON proposal, and `history/` preserves the preceding `current.json` when a candidate is adopted. Chat updates use the adopted complete JSON plus Calendar update material and return a new complete JSON; no candidate is adopted automatically.
- 2026-08-22, Issue #29: local real-trip viewing uses a Python-standard-library server bound only to `127.0.0.1`. Its read-only API exposes trip-list metadata and adopted `current.json` files only; it never exposes `candidate.json`, `history/`, or a general `Calendar_Local` static path. Static review hosting keeps the synthetic sample fallback.

## Pending

- GitHub repository visibility.
- Production application platform and framework after the read-only prototype.
- Build, test, formatting, and review commands.
- Detailed JSON Schema and publication model.

Record a decision here only after it is explicitly confirmed. Include the date, context, decision, and consequences when implementation begins.
