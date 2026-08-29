# Calendar

Calendar is the first standard project in `/Users/us/Tools`, built with a three-layer layout that lets Codex discover the right information without repeated path instructions.

## Current baseline

CAL is the domain foundation for personal time and plans, centered on
`Trip / Event / Todo`. It uses a hybrid data model under private
`Calendar_Local` storage: SQLite manages structured CAL-wide state, while a
formal complete Trip JSON is the last AI-generated and validated authoritative
base for each itinerary. The currently visible `effective Trip` combines that
base with active Direct Overrides stored in SQLite. See
[`docs/calendar-baseline.md`](docs/calendar-baseline.md).

The repository still contains the dependency-free, read-only Trip JSON
prototype. Its Web architecture is legacy, but the formal Trip JSON, Schema,
stable IDs, validation, and complete-JSON regeneration method are reuse targets
in the rebuilt baseline. No existing data or code has been migrated or removed.

## Three layers

| Role | Location | Authority |
| --- | --- | --- |
| Development | `/Users/us/Tools/Development/Calendar_Dev` | Git-managed source, confirmed specifications, tests, Issues, and PRs |
| Shared references | `/Users/us/Tools/GoogleDrive/Calendar_GD` | Reference documents, screenshots, and Chat/Work handoffs |
| Private local data | `/Users/us/Tools/LocalData/Calendar_Local` | Non-shared inputs, runtime data, caches, and temporary data |

## Repository map

- `AGENTS.md`: durable Codex rules and discovery order
- `docs/project-structure.md`: boundaries and information flow
- `docs/workflow.md`: future Issue-to-PR workflow
- `docs/decisions.md`: confirmed architectural decisions
- `docs/calendar-baseline.md`: current confirmed CAL responsibilities and data baseline
- `docs/calendar-specification.md`: retained Trip JSON specification subject to scoped reuse
- `Schemas/trip.schema.json`: current formal Trip JSON contract and reuse baseline
- `docs/trip-json-generation.md`: retained complete-Trip-JSON generation workflow
- `docs/operation.md`: current Trip JSON operation until the hybrid flow is implemented
- `Sources/`: application source code when implementation starts
- `Tests/`: automated tests and test guidance
- `Samples/`: synthetic, non-sensitive examples safe to commit

## Starting work

Open this repository as the Codex project. Codex reads `AGENTS.md`, then follows this README and only the task-relevant links. Human contributors should also begin with `AGENTS.md` and check Git status before editing.

## Validation

Run all dependency-free project checks:

```sh
sh Tests/run.sh
```

The command validates committed JSON samples and runs every `Tests/*.test.sh`
script. Pull requests to `main` run the same command in GitHub Actions, together
with a diff consistency check. Add other build and test commands here when the
technology stack is selected.

## Legacy prototype preview

From the repository root, start the loopback-only read server:

```sh
python3 scripts/serve_calendar.py
```

Open `http://127.0.0.1:4174/Sources/web/`. The server exposes only formal
`trips/<trip-id>.json` files through read-only routes; it does not expose the
rest of `Calendar_Local`.

Tests can override the private-data root with `--local-data PATH` or the
`CALENDAR_LOCAL_DATA` environment variable. The server always binds to
`127.0.0.1`.

Real trip data is kept outside this repository. See
[`docs/operation.md`](docs/operation.md) before viewing or updating it.

Validate a ChatGPT-generated complete JSON before previewing it:

```sh
python3 scripts/validate_trip.py /path/to/trip.json
```
