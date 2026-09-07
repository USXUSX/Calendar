# Calendar

Calendar is the first standard project in `/Users/us/Tools`, built with a three-layer layout that lets Codex discover the right information without repeated path instructions.

## Current baseline

Goal 1の新規Trip主要経路は、Chatで完全Trip JSONを生成し、CALでValidation・取込・表示・編集する方式である。取込後の編集は微修正に限定しない。
[生成・受渡しガイド](docs/trip-json-generation.md)と[JSON取込契約](docs/trip-json-import.md)を参照する。
共有candidateの一覧・読込・Validation・確認から`import_trip_json`で新規採用する（#110）。
Frameの`/calendar/import`はこのJSON経路を主要入口とし、1予定追加コピペは別経路として維持する。
旧日本語ラベルの全Trip commandは互換用に保持するが、主要UIからは外した。
既存Tripは#112の[継続Chat往復](docs/trip-json-generation.md#継続するchat往復112)を使える。
CALが`GoogleDrive/Calendar_Chat/<trip-id>/`へ最新contextを自動共有し（#114）、
FrameでChat指示追加とcandidateの変更確認・保留・明示反映を行う。
Calendar_GDはGit参照コピー、Calendar_Localは正式Trip/SQLiteのまま分離する。
正式Trip/SQLiteはCALだけが更新する。
物理iPad miniの実用性・Phase 8振り返り・初期リリース判断は#96に残る。

Issue #116でChat往復を主要経路とし、CAL内の候補検索・AFM推薦・コメントAIとFrameのWorking/AI編集UIを撤去した。
通常画面の予定追加（直接/1予定コピペ）、削除、並び替え、候補Placeの選択は
[直接操作契約](docs/direct-schedule.md)を使う。正式Place補完は選択状態に依存しない。
Mac確認までを今回の到達点とし、物理iPad mini受入・Phase振り返り・初期リリース判断は#96に残る。

共通施設取得と⑥Place補完は`get_place_enrichment`で取得し、stable Placeは
`adopt_place_enrichment`で明示確認済みの不足値だけをDirect Overrideへ正式採用する。
Workingは作成・変更せず、temporary itemは`prepare_place_enrichment`による候補準備までとする。
Wikidataの保存可能fieldと一時根拠を分け、明示選択後も既存の非空値は保持する。
[取得adapterと採用接続](docs/place-acquisition.md)を参照する。

通常手動編集は予定の`edit_trip_item`と日別代表エリアの`edit_trip_day`を使い、
Direct Overrideへ保存して`get_trip_detail_view`から再表示する。
`edit_trip_day(command_id, trip_id, day_id, {"route_summary": value})`は既存の
`Day.routeSummary`だけを更新し、Workingを作成・変更しない。
日付行・編集sheetの接続はFrame Issue #39で扱う。

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

Phase 6 Working regeneration uses a separate latest-only CAL state per Trip.
No row means `idle`; a row fixes one generation identity, `auto` / `review`
current adoption policy, the frozen Working export package and canonical Working digest, the captured revision, and only the current minimal state and
candidate or safe terminal result. It does not retain a queue, retry count,
history, or provider/model metadata.
After formal Validation, auto candidates are checked for explicit structured Working
field mismatches, Trip summary changes, and unrequested ScheduleItem/Transport removal.
A signal atomically promotes the same generation to `review / candidate_ready`;
confirmation and adoption use the existing review path. Policy means the current
adoption policy, not a retained record of the initial choice. No automatic downgrade,
repair, retry, or complete intent/preservation guarantee is added.
Rule evaluation errors become the fixed CAL failure `diff_check_failed`. Promotion
database write errors raise `GenerationWriteError` without claiming a failed or ready
transition; the transaction rolls back. Old or duplicate results raise Conflict and
cannot terminalize a different generation or an already retained candidate.
After adoption clears Working, `start_working_trip()` is the semantic command for
starting a new empty Working state from the current effective Trip. Callers do not
construct or persist the empty Working envelope themselves.

For explicitly authorized synthetic/live diagnostics, call
`diagnose_working_trip_generation_candidate(trip_id, generation_id, candidate)`
before normal AIG result reception. It reuses the current Working/stale gate and
Phase 5 checks, returning only `valid`, `schema`, `semantic_reference`, or
`constraint`. The semantic label covers the existing semantic consistency checks,
including references and dates. It returns no values, field paths, exception text,
or candidate and writes no state. Obsolete/stale workflow errors still raise;
they are not candidate classifications. `valid` does not establish that a user's
intent was satisfied or authorize adoption.

Normal result reception and adoption still run their own checks. External result,
generation state and FRM behavior are unchanged (`invalid_candidate` for Validation
failures; existing constraint conflicts can remain `obsolete_working`). Diagnostics
do not retain failed candidates or enable retries. Keep live request/response and
candidate bodies in memory, report only the fixed stage, and do not invoke the
normal review candidate-storage path merely to diagnose a failure.

For FRM's unapplied candidate timeline, call
`get_working_trip_generation_candidate_preview(trip_id, generation_id)`.
Only the latest current `review / candidate_ready` generation can return a
read-only `view` using the existing Trip-detail timeline shape. Raw candidate
and generation internals are excluded; entry edit/AI targets are disabled.
See [`docs/trip-detail-model.md`](docs/trip-detail-model.md) for the preview and
confirmation contract.

## Three layers

| Role | Location | Authority |
| --- | --- | --- |
| Development | `/Users/us/Tools/Development/Calendar_Dev` | Git-managed source, confirmed specifications, tests, Issues, and PRs |
| Shared references | `/Users/us/Tools/GoogleDrive/Calendar_GD` | One-way reference copy of committed Git source |
| Private local data | `/Users/us/Tools/LocalData/Calendar_Local` | Non-shared inputs, runtime data, caches, and temporary data |

## Repository map

- `AGENTS.md`: durable Codex rules and discovery order
- `docs/project-structure.md`: boundaries and information flow
- `docs/workflow.md`: current TDS entry and Calendar reference-copy handling
- `docs/decisions.md`: confirmed architectural decisions
- `docs/calendar-baseline.md`: current confirmed CAL responsibilities and data baseline
- `docs/initial-release.md`: Goal 1 scope, Chat paste format, and external data acquisition / retention policy
- `docs/development-roadmap.md`: CAL's final usage vision and current Goal / Phase / Step roadmap
- `docs/calendar-specification.md`: retained Trip JSON specification subject to scoped reuse
- `docs/trip-detail-ui.md`: confirmed iPad mini / iPad itinerary-detail UI requirements
- `docs/trip-detail-model.md`: Phase 1 UI display derivation and semantic update boundaries
- `Schemas/trip.schema.json`: current formal Trip JSON contract and reuse baseline
- `Schemas/calendar-v3.sql`: current reproducible SQLite schema, including Working Trip state
- `Schemas/calendar-v2.sql`: retained schema revision for Trip versions and generation requests
- `Schemas/calendar-v1.sql`: retained initial SQLite schema revision
- `docs/trip-json-generation.md`: current new-Trip complete-JSON generation and candidate handoff
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
