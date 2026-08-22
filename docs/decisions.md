# Architecture decisions

## Confirmed

- Project root: `/Users/us/Tools`.
- Three layers: `Development`, `GoogleDrive`, and `LocalData`, each with a `Calendar` project folder.
- GitHub will be the canonical system for code, confirmed specifications, Issues, Pull Requests, and tests.
- GitHub repository: `USXUSX/Calendar`; local `origin` points to `git@github.com:USXUSX/Calendar.git`.
- The existing Calendar prototype will not be migrated during foundation setup.
- 2026-08-20, Issue #5: the first read-only UI uses browser-native HTML, CSS, and ES modules with no application framework or runtime dependencies. It is served locally as static files, reads only committed synthetic JSON, and exists to validate the display contract and information design before a production architecture is selected.
- 2026-08-22, Issue #33: Calendar displays only the formal JSON structure. Legacy compatibility is removed; old data is corrected or regenerated once instead of normalized on every view. Private trips use one file per trip at `Calendar_Local/trips/<trip-id>.json`. The loopback-only Python server remains only as the minimal read-only bridge needed for a browser to list and load Git-external files; candidate/history management and write APIs are not part of Calendar.
- 2026-08-22, Issue #38: `Schemas/trip.schema.json` is the formal machine-readable trip contract. ChatGPT generates a complete JSON with explicit nullable fields, and Calendar accepts it only after structural and cross-reference validation. Existing fixtures and legacy shapes do not constrain the contract and no compatibility conversion is added.

## Pending

- GitHub repository visibility.
- Production application platform and framework after the read-only prototype.
- Build, test, formatting, and review commands.
- Publication model.

Record a decision here only after it is explicitly confirmed. Include the date, context, decision, and consequences when implementation begins.
