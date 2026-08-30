# Sources

`calendar_domain/` contains the CAL-owned semantic domain interface. It is a
Python standard-library package over the SQLite v2 schema and formal Trip JSON:

- `service.py`: unified Event/effective Trip reads, transactional commands,
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

`calendar_worker.py` is the CAL-owned one-shot execution boundary. It recovers
interrupted adoptions, claims at most one request, invokes a replaceable
semantic-payload-to-Patch generator, and submits through `CalendarDomain`.
Generator launch failures are released for retry; stale submissions are
requeued by the domain; validation or semantic conflicts stop that request's
automatic retry while leaving the Instruction pending for human review.

`web/` contains the dependency-free, read-only prototype for Issue #5. From the
repository root, serve the project with:

```sh
python3 -m http.server 4173
```

Then open `http://localhost:4173/Sources/web/`. The prototype only fetches
committed synthetic JSON from `Samples/`; it has no write path or external API.
