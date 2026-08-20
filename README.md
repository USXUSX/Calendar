# Calendar

Calendar is the first standard project in `/Users/us/Tools`, built with a three-layer layout that lets Codex discover the right information without repeated path instructions.

## Current state

The first dependency-free, read-only web prototype is implemented from a synthetic JSON sample. No legacy prototype or private data has been migrated, and no production framework has been selected.

## Three layers

| Role | Location | Authority |
| --- | --- | --- |
| Development | `/Users/us/Tools/Development/Calendar` | Git-managed source, confirmed specifications, tests, Issues, and PRs |
| Shared references | `/Users/us/Tools/GoogleDrive/Calendar` | Reference documents, screenshots, and Chat/Work handoffs |
| Private local data | `/Users/us/Tools/LocalData/Calendar` | Non-shared inputs, runtime data, caches, and temporary data |

## Repository map

- `AGENTS.md`: durable Codex rules and discovery order
- `docs/project-structure.md`: boundaries and information flow
- `docs/workflow.md`: future Issue-to-PR workflow
- `docs/decisions.md`: confirmed architectural decisions
- `docs/calendar-specification.md`: confirmed Calendar data and AI-assisted update specification
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

## Local preview

From the repository root:

```sh
python3 -m http.server 4173
```

Open `http://localhost:4173/Sources/web/`. The preview is local and read-only;
it does not publish or connect to external services.
