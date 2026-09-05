# Sources

`calendar_domain/` contains the CAL-owned semantic domain interface. It is a
Python standard-library package over the SQLite v3 schema and formal Trip JSON:

- `service.py`: unified Event/effective/Working Trip reads, transactional commands,
  generation-request claim/retry, JSON Patch handling, and validated atomic
  adoption with digest-journal recovery
- `models.py`: source-qualified unified Event read model
- `errors.py`: not-found, validation, and conflict domain boundary

Consumers construct `CalendarDomain` with an explicit database path and Trip
root. No production location is selected by default. Workers claim a semantic
payload containing the Instruction, complete base Trip, logical version, and
digest, then submit only an `add` / `remove` / `replace` JSON Patch. They do not
manage SQLite tables, file paths, complete candidates, atomic replacement, or
the private recovery journal.

Working confirmation accepts a generator-neutral complete candidate JSON object
through `adopt_working_trip_candidate(trip_id, candidate)`. The command confirms
that the registered Trip has one Working target and, immediately before accepting
the candidate, requires its captured effective revision to equal the current
effective revision. A stale target raises Conflict without automatic rebase or
merge. It then reuses the existing complete-candidate gate for formal Schema,
semantic/cross-reference, Trip ID, active Direct Override effective-Trip, and
Todo stable-item-reference validation. It does not accept a candidate file path,
persist a candidate queue, or identify a generator. A validated candidate is passed
to the same generator-neutral same-filesystem atomic replacement and digest-journal
recovery layer used by the Patch pipeline. Successful adoption increments the Trip
version and clears only the target Working row; active Direct Overrides remain. If
recovery finds the candidate current it completes the version update and Working
clear, while an unchanged old current keeps Working state.

Phase 6 Working generation uses `aig_trip_generation.py` to send the exact
`generation_id`, `trip_id`, and frozen Working export package over a replaceable JSON
stdin/stdout AIG command. Result receipt rechecks the Working-content digest and sends a
complete candidate through the shared Phase 5 formal Validation boundary. The policy
is the current adoption policy. After formal Validation, `auto` passes the limited
rules in `calendar_domain/candidate_diff.py`; no signal continues through the Phase 5
Working-content gate and atomic adoption. A signal uses
`promote_working_trip_generation_candidate()` to atomically set `policy=review`,
retain that candidate, and enter `candidate_ready`. The same transaction checks the
current generation, Working, effective revision, and adoption constraints.
An existing `review` generation retains its candidate without requiring these rules. Review
confirmation uses the same gate and adoption boundary. Success records only `adopted`,
the new Trip version, and candidate digest on the latest generation.

`diff_check_failed` is a CAL-local terminal classification for rule evaluation errors,
including unsupported structured fields. Promotion DB write failures raise
`GenerationWriteError` and roll back without a terminal-state claim. A zero-row
conditional transition is Conflict; stale/constraint validation keeps the existing
failure mapping. No original-policy, rule-reason history, or inspection-version
columns are added. Re-evaluated reasons would describe current rules, not historical
evidence. The AIG request/result contract is unchanged.

`calendar_worker.py` is the CAL-owned one-shot execution boundary. It recovers
interrupted adoptions, claims at most one request, invokes a replaceable
semantic-payload-to-Patch generator, and submits through `CalendarDomain`.
Generator launch failures are released for retry; stale submissions are
requeued by the domain; validation or semantic conflicts stop that request's
automatic retry while leaving the Instruction pending for human review.

`openai_patch_generator.py` is one provider implementation of that external
generator contract. It accepts only the semantic claim on stdin, calls the
OpenAI Responses API with Structured Outputs and no tools, validates the
returned Patch shape, and writes only the Patch array to stdout. API keys come
only from `OPENAI_API_KEY`; the model must be supplied by CLI or environment.
It is not imported by `calendar_domain` or `calendar_worker`.

`web/` contains the dependency-free, read-only prototype for Issue #5. From the
repository root, serve the project with:

```sh
python3 -m http.server 4173
```

Then open `http://localhost:4173/Sources/web/`. The prototype only fetches
committed synthetic JSON from `Samples/`; it has no write path or external API.
