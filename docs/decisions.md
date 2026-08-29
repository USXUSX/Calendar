# Architecture decisions

## Historical confirmed decisions

- Project root: `/Users/us/Tools`.
- Three layers: `Development`, `GoogleDrive`, and `LocalData`, each with a `Calendar` project folder.
- GitHub will be the canonical system for code, confirmed specifications, Issues, Pull Requests, and tests.
- GitHub repository: `USXUSX/Calendar`; local `origin` points to `git@github.com:USXUSX/Calendar.git`.
- The existing Calendar prototype will not be migrated during foundation setup.
- 2026-08-20, Issue #5: the first read-only UI uses browser-native HTML, CSS, and ES modules with no application framework or runtime dependencies. It is served locally as static files, reads only committed synthetic JSON, and exists to validate the display contract and information design before a production architecture is selected.
- 2026-08-22, Issue #33: Calendar displays only the formal JSON structure. Legacy compatibility is removed; old data is corrected or regenerated once instead of normalized on every view. Private trips use one file per trip at `Calendar_Local/trips/<trip-id>.json`. The loopback-only Python server remains only as the minimal read-only bridge needed for a browser to list and load Git-external files; candidate/history management and write APIs are not part of Calendar.
- 2026-08-22, Issue #38: `Schemas/trip.schema.json` is the formal machine-readable trip contract. ChatGPT generates a complete JSON with explicit nullable fields, and Calendar accepts it only after structural and cross-reference validation. Existing fixtures and legacy shapes do not constrain the contract and no compatibility conversion is added.

## Active baseline

- 2026-08-30, Issue #46: CAL is the domain foundation for personal time and plans, centered on `Trip / Event / Todo`. `Task` is not a CAL domain term; it is reserved for the separate Task / TSK tool, whose execution unit is `Job`. A trip itinerary is principally a chronological view of `Event` records belonging to a `Trip`, and a `Todo` may relate to a `Trip` or `Event`.
- 2026-08-30, Issue #46: Canonical real data will be SQLite under `/Users/us/Tools/LocalData/Calendar_Local`, with `/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3` as the first placement candidate. JSON is an exchange format for AI generation, import/export, external integration, validation, and samples; it is not the canonical store. The physical schema and access interface remain follow-up decisions.
- 2026-08-30, Issue #46: CAL owns its domain data and meaning-based read/write boundary. FRM is the owner-facing Web entry and must not manipulate CAL's physical SQLite schema. TSK schedules and executes Mac `Job` records and receives only explicitly integrated automated work, not a full CAL sync. ENT remains a separate acquisition/storage foundation and does not share a database with CAL.
- 2026-08-30, Issue #46: Participant access must use a read-only model derived from owner data. CAL's SQLite and owner read/write boundary are never exposed directly. Initial visibility uses `owner` and `participants`; `Trip` and `Event` are the primary shareable entities, while future explicit `Todo` sharing remains possible. Projection, authentication, URL, hosting, and publication are follow-up decisions, and no participant publication is authorized by this decision.

## Superseded

- 2026-08-20, Issue #5 is superseded as an application baseline by Issue #46. Its dependency-free, read-only UI remains a legacy prototype and migration reference; its technology choices do not select the rebuilt CAL platform.
- 2026-08-22, Issue #33 is superseded by Issue #46 where it makes one private JSON file per trip the canonical real-data model and the Calendar-hosted read-only itinerary Web the central architecture. Its legacy compatibility and server behavior remain descriptive of the retained prototype only.
- 2026-08-22, Issue #38 is superseded by Issue #46 where it makes the complete trip JSON Schema the CAL-wide canonical data contract and complete-JSON regeneration the primary update path. The Schema and validator remain valid for legacy exchange data until a separate migration or cleanup Issue changes them.

## Pending

- GitHub repository visibility.
- Production application platform and framework after the read-only prototype.
- SQLite physical schema, domain interface, and migration strategy.
- FRM-to-CAL access method and owner read/write contracts.
- Participant projection, authentication, publication, and refresh model.
- Build, test, formatting, and review commands for the rebuilt implementation.
- Publication model.

Record a decision here only after it is explicitly confirmed. Include the date, context, decision, and consequences when implementation begins.
