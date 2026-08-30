# Tests

Run the canonical dependency-free validation from the repository root:

```sh
sh Tests/run.sh
```

`run.sh` parses every JSON file under `Samples/` and runs each
`Tests/*.test.sh` script. New dependency-free shell tests can therefore join the
standard local and GitHub Actions checks by following that filename pattern.

`trip-schema.test.sh` verifies the formal JSON Schema, semantic reference
validation, and the ChatGPT generation guide. Existing legacy fixtures are not
kept as compatibility cases.

`read-only-ui.test.sh` validates the synthetic trip contract and confirms that
the static prototype contains no network write or external-service path.

`temporary-state-ui.test.sh` confirms that Issue #9 interactions use separate
browser-memory state and do not add instructions or draft fields to the adopted
synthetic JSON.

`sqlite-schema.test.sh` initializes a temporary empty SQLite database and
validates the v1 tables, schema version, foreign keys, enums, relationship
constraints, AI Instruction state, Direct Override uniqueness, and JSON values.

`calendar-domain.test.sh` uses only a temporary SQLite database and a copied
synthetic Trip root. It covers unified ordinary/Trip Events and source-qualified
identities, effective Trip composition without JSON writes, invalid Overrides,
ordinary Event and Todo CRUD, Todo completion, AI Instruction cancellation,
Trip registration, explicit storage paths, and transactional rollback.

`candidate-adoption.test.sh` uses only a temporary SQLite database and synthetic
Trip root. It covers complete candidate validation, Trip ID matching, explicit
Instruction application, atomic replacement failures, active Override and Todo
item constraints, post-adoption effective Trips, and both digest-journal
recovery outcomes. It never reads or writes `Calendar_Local`.
