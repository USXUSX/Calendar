# Calendar

Calendar is the first standard project in `/Users/us/Tools`, built with a three-layer layout that lets Codex discover the right information without repeated path instructions.

## Current state

Foundation only. No existing Calendar prototype has been migrated, and no application framework has been selected.

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
- `Sources/`: application source code when implementation starts
- `Tests/`: automated tests and test guidance
- `Samples/`: synthetic, non-sensitive examples safe to commit

## Starting work

Open this repository as the Codex project. Codex reads `AGENTS.md`, then follows this README and only the task-relevant links. Human contributors should also begin with `AGENTS.md` and check Git status before editing.

No build or test command exists yet. Record commands here when the technology stack is selected.
