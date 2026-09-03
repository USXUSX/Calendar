# Calendar

Calendar is the first standard project in `/Users/us/Tools`, built with a three-layer layout that lets Codex discover the right information without repeated path instructions.

## Current baseline

CAL is the domain foundation for personal time and plans, centered on
`Trip / Event / Todo`. It uses a hybrid data model under private
`Calendar_Local` storage: SQLite manages structured CAL-wide state, while a
formal complete Trip JSON is the last CAL-adopted and validated authoritative
base for each itinerary. The currently visible `effective Trip` combines that
base with active Direct Overrides stored in SQLite. See
[`docs/calendar-baseline.md`](docs/calendar-baseline.md).

The repository still contains the dependency-free, read-only Trip JSON
prototype. Its Web architecture is legacy, but the formal Trip JSON, Schema,
stable IDs, validation, and complete-JSON regeneration method are reuse targets
in the rebuilt baseline. No existing data or code has been migrated or removed.

`Sources/calendar_domain/` provides the dependency-free CAL semantic domain
interface over SQLite v3. Callers supply an explicit SQLite path and Trip data root, then
use this interface for unified Events, effective Trips, Todos, and change-input
commands; they do not query CAL tables or inspect Trip JSON file layout.
It also owns the AI Instruction Patch pipeline. Instruction registration queues
one generation request; claim returns a semantic base payload with version and
hash; the worker returns only JSON Patch. CAL applies the Patch to an in-memory
copy, validates the complete candidate against Schema, semantic references,
active Overrides, and Todo item references, then atomically adopts it.

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
- `docs/development-roadmap.md`: CAL's final usage vision and current Goal / Phase / Step roadmap
- `docs/calendar-specification.md`: retained Trip JSON specification subject to scoped reuse
- `docs/trip-detail-ui.md`: confirmed iPad mini / iPad itinerary-detail UI requirements
- `docs/trip-detail-model.md`: Phase 1 UI display derivation and semantic update boundaries
- `Schemas/trip.schema.json`: current formal Trip JSON contract and reuse baseline
- `Schemas/calendar-v3.sql`: current reproducible SQLite schema, including Working Trip state
- `Schemas/calendar-v2.sql`: retained schema revision for Trip versions and generation requests
- `Schemas/calendar-v1.sql`: retained initial SQLite schema revision
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

Initialize a new empty development or temporary database only with an explicit
path:

```sh
python3 scripts/init_calendar_db.py /path/to/new/calendar.sqlite3
```

The initializer refuses a non-empty target and has no production-data default.

The command validates committed JSON samples and runs every `Tests/*.test.sh`
script. Pull requests to `main` run the same command in GitHub Actions, together
with a diff consistency check. Add other build and test commands here when the
technology stack is selected.

The domain interface has no production path default:

```python
from Sources.calendar_domain import CalendarDomain

calendar = CalendarDomain("/explicit/path/calendar.sqlite3", "/explicit/trip-root")
events = calendar.list_events("2027-05-01", "2027-05-31")
instruction = calendar.add_ai_instruction("instruction-id", "trip-id", "Change the second day")
request = calendar.claim_generation_request()
result = calendar.submit_json_patch(
    request["request_id"], request["instruction_id"], request["trip_id"], patch,
    request["base_version"], request["base_hash"],
)
```

TSK等のJob runnerはCAL内部状態を操作せず、明示pathとgenerator argvを指定して
one-shot workerだけを起動する。1回で最大1 requestを処理し、queued requestが
なければ正常にno-op終了する。

```sh
python3 scripts/run_generation_worker.py \
  --db /explicit/path/calendar.sqlite3 \
  --trip-root /explicit/trip-root \
  -- /path/to/patch-generator --its-option
```

generatorはstdinのCAL semantic claim payloadを読み、stdoutへJSON Patch配列だけを
返す。provider接続、認証、model選択、実運用TSK設定はこのworkerの責務ではない。

OpenAI Responses API adapterをgeneratorとして使う場合も、API keyとmodelを
CAL coreへ固定しない。keyは`OPENAI_API_KEY`だけから読み、modelは`--model`または
`OPENAI_MODEL`で明示する。

```sh
python3 scripts/run_generation_worker.py \
  --db /explicit/path/calendar.sqlite3 \
  --trip-root /explicit/trip-root \
  -- python3 scripts/generate_openai_patch.py --model <model-id>
```

通常testはmock transportだけを使い、実API、credential、課金を必要としない。

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
