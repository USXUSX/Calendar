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

`web/` contains the dependency-free, read-only prototype for Issue #5. From the
repository root, serve the project with:

```sh
python3 -m http.server 4173
```

Then open `http://localhost:4173/Sources/web/`. The prototype only fetches
committed synthetic JSON from `Samples/`; it has no write path or external API.
