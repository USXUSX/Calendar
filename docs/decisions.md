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

- 2026-08-30, Issue #46: CAL is the domain foundation for personal time and plans, centered on `Trip / Event / Todo`. `Task` is not a CAL domain term; it is reserved for the separate Task / TSK tool, whose execution unit is `Job`. A `Todo` may relate to a `Trip` or `Event`; the mapping between Trip itinerary items and CAL `Event` records remains a follow-up decision.
- 2026-08-30, Issue #46: CAL uses a hybrid data foundation under `/Users/us/Tools/LocalData/Calendar_Local`. SQLite, with `db/calendar.sqlite3` as the first placement candidate, manages CAL-wide Trip metadata, ordinary `Event` and `Todo` records, relationships, change inputs, direct changes, share/visibility, and other structured state. A formal complete Trip JSON is the authoritative current itinerary representation for each trip and may also serve AI generation, import/export, and external integration. The SQLite schema and its synchronization/reference boundary with Trip JSON remain follow-up decisions.
- 2026-08-30, Issue #46: Trip itinerary changes have two distinct input paths. `AI Instruction` records natural-language intent for AI interpretation; `Direct Override` records concrete user-specified values and must remain an input to later regeneration so it is not lost. The next complete Trip JSON is regenerated from the current Trip JSON, AI Instructions, and Direct Overrides. Finer hard/soft classification and input lifecycle remain follow-up decisions.
- 2026-08-30, Issue #46: CAL owns its domain data and meaning-based read/write boundary. FRM is the owner-facing Web entry and must not manipulate CAL's physical SQLite schema. TSK schedules and executes Mac `Job` records and receives only explicitly integrated automated work, not a full CAL sync. ENT remains a separate acquisition/storage foundation and does not share a database with CAL.
- 2026-08-30, Issue #46: Participant access must use a read-only model derived from owner data. CAL's SQLite, owner-use Trip JSON, and owner read/write boundary are never exposed directly. Initial visibility uses `owner` and `participants`; `Trip` and `Event` are the primary shareable entities, while future explicit `Todo` sharing remains possible. Projection, authentication, URL, hosting, and publication are follow-up decisions, and no participant publication is authorized by this decision.

## Superseded

- 2026-08-20, Issue #5 is superseded as an application baseline by Issue #46. Its dependency-free, read-only UI remains a legacy prototype and migration reference; its technology choices do not select the rebuilt CAL platform.
- 2026-08-22, Issue #33 is superseded only where it makes the Calendar-hosted read-only itinerary Web the central CAL architecture and uses Trip JSON alone for all CAL-wide state. One formal complete JSON per Trip remains the current itinerary representation; legacy server behavior remains descriptive of the retained prototype only.
- 2026-08-22, Issue #38 is retained for the formal complete Trip JSON, JSON Schema, stable-ID continuity, cross-reference validation, and AI complete-JSON regeneration method. It is superseded only where the Trip contract is treated as the contract for all CAL data rather than one part of the SQLite/Trip-JSON hybrid foundation.

## Pending

- GitHub repository visibility.
- Production application platform and framework after the read-only prototype.
- SQLite physical schema, domain interface, and migration strategy.
- SQLite-to-Trip-JSON synchronization/reference, atomic update, history, and rollback strategy.
- `AI Instruction / Direct Override` persistence, lifecycle, conflict, and removal rules.
- FRM-to-CAL access method and owner read/write contracts.
- Participant projection, authentication, publication, and refresh model.
- Build, test, formatting, and review commands for the rebuilt implementation.
- Publication model.

Record a decision here only after it is explicitly confirmed. Include the date, context, decision, and consequences when implementation begins.
