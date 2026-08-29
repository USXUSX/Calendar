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

- 2026-08-30, Issue #46: CAL is the domain foundation for personal time and plans, centered on `Trip / Event / Todo`. `Task` is not a CAL domain term; it is reserved for the separate Task / TSK tool, whose execution unit is `Job`. A `Todo` may relate to a `Trip` or `Event`.
- 2026-08-30, Issue #46 and #48: CAL uses a hybrid data foundation under `/Users/us/Tools/LocalData/Calendar_Local`. SQLite, with `db/calendar.sqlite3` as the first placement candidate, is authoritative for CAL-wide Trip metadata, ordinary `Event` and `Todo` records, relationships, change inputs, share/visibility, and other structured state. A formal complete Trip JSON is the last AI-generated and validated authoritative itinerary base. The current owner-visible `effective Trip` is derived from that Trip JSON plus active Direct Overrides stored in SQLite.
- 2026-08-30, Issue #46: Trip itinerary changes have two distinct input paths. `AI Instruction` records natural-language intent for AI interpretation; `Direct Override` records concrete user-specified values and must remain an input to later regeneration so it is not lost. The next complete Trip JSON is regenerated from the current Trip JSON, AI Instructions, and Direct Overrides. Finer hard/soft classification and input lifecycle remain follow-up decisions.
- 2026-08-30, Issue #48: Trip itinerary items such as `scheduleItem` and `transport` remain authoritative in formal Trip JSON and are not duplicated as authoritative SQLite `Event` rows. Unified Schedule and Today read models combine ordinary SQLite Events with derived Trip Events projected from Trip JSON. A projected Trip Event retains source identity through the Trip ID and existing stable source-item ID; any persisted projection is only a regenerable cache.
- 2026-08-30, Issue #48: A Direct Override targets a Trip item by stable ID, is stored as active SQLite state, and changes the `effective Trip` immediately without rewriting Trip JSON. It is not automatically consumed or deleted after JSON regeneration and remains a constraint for later regeneration. An AI Instruction records natural-language intent but does not change the effective Trip until a successful regeneration adopts a new validated Trip JSON. Detailed lifecycle, conflict, removal, applied-state, and hard/soft rules remain pending.
- 2026-08-30, Issue #48: Regeneration produces a candidate complete Trip JSON from the current Trip JSON, pending AI Instructions, and active Direct Overrides. Only a candidate that passes the existing JSON Schema, stable-ID, cross-reference, and other required validation becomes current. AI or validation failure preserves the current Trip JSON, active Direct Overrides, and unprocessed AI Instructions; incomplete JSON is never presented as current. Detailed history, backup, and rollback are pending.
- 2026-08-30, Issue #48: Update commands preserve source authority even in a unified Schedule. Editing an ordinary Event updates its SQLite Event record. Editing a projected Trip Event registers a Direct Override or AI Instruction against its Trip source and never converts it into an authoritative ordinary SQLite Event.
- 2026-08-30, Issue #46: CAL owns its domain data and meaning-based read/write boundary. FRM is the owner-facing Web entry and must not manipulate CAL's physical SQLite schema. TSK schedules and executes Mac `Job` records and receives only explicitly integrated automated work, not a full CAL sync. ENT remains a separate acquisition/storage foundation and does not share a database with CAL.
- 2026-08-30, Issue #46 and #48: Participant access must use a read-only model derived from the effective Trip and SQLite visibility/share state. CAL's SQLite, Trip JSON files, Direct Overrides, AI Instructions, and owner read/write boundary are never exposed directly. Initial visibility uses `owner` and `participants`; `Trip` and `Event` are the primary shareable entities, while future explicit `Todo` sharing remains possible. Projection, authentication, URL, hosting, and publication are follow-up decisions, and no participant publication is authorized by this decision.
- 2026-08-30, Issue #50: `Schemas/calendar-v1.sql` is the reproducible physical SQLite v1 schema for CAL-wide state. It contains `schema_meta`, Trip registry state, ordinary Events, Todos, AI Instructions, and Direct Overrides. It intentionally contains no authoritative Trip itinerary fields and no authoritative Trip-derived Event rows. Every connection must enable SQLite foreign keys.
- 2026-08-30, Issue #50: A new AI Instruction starts as `pending`; generation or Validation failure leaves it pending, successful adoption of a candidate that used it changes it to `applied`, and user cancellation changes it to `cancelled`. Direct Overrides keep one current row per `trip_id + source_item_id + field_path`; re-editing updates that row, disabling sets `active = 0`, and successful AI regeneration does not consume it.
- 2026-08-30, Issue #52: `Sources/calendar_domain/` is CAL's Python semantic domain interface v1. It is an internal storage boundary, not a CAL UI platform decision. Callers explicitly inject the SQLite path and Trip root and use meaning-based reads and commands instead of SQLite tables, Trip file paths, or JSON collection layout. Unified Event identities are source-qualified; Trip projection uses effective Trip data and never creates authoritative `events` rows.
- 2026-08-30, Issue #52: Effective Trip composition deep-copies the validated authoritative Trip JSON, applies active Direct Overrides in memory by stable source item ID and item-relative JSON Pointer, then validates the complete result. Invalid or ambiguous items, paths, and values are domain errors, and the authoritative JSON is never rewritten. Each SQLite command is one transaction; physical SQLite and filesystem errors are translated to a small not-found / validation / conflict boundary.

## Superseded

- 2026-08-20, Issue #5 is superseded as an application baseline by Issue #46. Its dependency-free, read-only UI remains a legacy prototype and migration reference; its technology choices do not select the rebuilt CAL platform.
- 2026-08-22, Issue #33 is superseded only where it makes the Calendar-hosted read-only itinerary Web the central CAL architecture and uses Trip JSON alone for all CAL-wide state. One formal complete JSON per Trip remains the last AI-generated and validated authoritative itinerary base; the effective Trip adds active Direct Overrides. Legacy server behavior remains descriptive of the retained prototype only.
- 2026-08-22, Issue #38 is retained for the formal complete Trip JSON, JSON Schema, stable-ID continuity, cross-reference validation, and AI complete-JSON regeneration method. It is superseded only where the Trip contract is treated as the contract for all CAL data rather than one part of the SQLite/Trip-JSON hybrid foundation.

## Pending

- GitHub repository visibility.
- Production application platform and framework after the read-only prototype.
- Migration strategy beyond the reproducible SQLite v1 initialization boundary.
- FRM-to-CAL adapter/access method over the implemented semantic domain interface.
- Candidate Trip JSON adoption atomicity and necessary history, backup, and rollback strategy.
- `AI Instruction / Direct Override` candidate consistency, conflict UI, and hard/soft rules beyond the v1 minimum lifecycle.
- FRM-to-CAL access method and owner read/write contracts.
- Participant projection, authentication, publication, and refresh model.
- Build, test, formatting, and review commands for the rebuilt implementation.
- Publication model.

Record a decision here only after it is explicitly confirmed. Include the date, context, decision, and consequences when implementation begins.
