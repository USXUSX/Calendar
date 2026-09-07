# Project structure

## Goal

Calendar uses one project name across three locations so Codex can resolve source, shared references, and private local data from a stable rule.

## Boundaries

### Development

`/Users/us/Tools/Development/Calendar_Dev` is the Git repository and the canonical location for source code, confirmed specifications, tests, and development history.

### Google Drive

`/Users/us/Tools/GoogleDrive/Calendar_GD` is a one-way reference copy of committed Git source. Git remains authoritative. Official synchronization and temporary review material follow `workflow.md`; do not add independent handoff files here.

### Local data

`/Users/us/Tools/LocalData/Calendar_Local` holds private or machine-specific data. It is outside Git and Google Drive. Code may read it through documented configuration later, but must not assume sample production data is safe to share.

Issues #46 through #54 establish a hybrid data foundation in this folder. Issue #71 extends the current schema to SQLite v3: v2 state remains unchanged and `working_trips` adds one latest-only Working state per Trip with its captured effective revision. Issue #75 adds `working_trip_generations` as a separate latest-only state/candidate row per Trip; an absent row is `idle`, and it does not add history, queueing, retries, or provider metadata. A formal complete Trip JSON is each trip's last CAL-validated and adopted authoritative itinerary base; AI returns JSON Patch and CAL constructs the complete candidate. The current `effective Trip` applies active Direct Overrides from SQLite. Ordinary Events remain authoritative in SQLite, while Trip-derived Events are projected from Trip JSON. Existing real data remains untouched.

`Calendar_GD/README.md` is the committed repository README, copied by official synchronization. `scripts/sync_folder_readmes.sh` only updates the private `Calendar_Local/README.md` from its Git template when that local maintenance is authorized; it does not update the shared copy.

## Discovery rule

The repository root is the only folder a user needs to open in Codex. `AGENTS.md` provides the two external locations and the inspection rules. Each external folder contains a small index explaining its role.

## Legacy boundary

`/Users/us/CommonTool/Calendar` is a separate legacy prototype. This new repository must not edit, move, import, or depend on it unless a future migration is explicitly approved.
