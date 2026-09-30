# Calendar project guidance

## Purpose

This repository is the canonical home for Calendar source code, confirmed specifications, tests, and GitHub Issue/PR work.

## Project locations

These are Local placements on Mac. Cloud tasks use the GitHub repository checkout and do not require these paths.

- Repository: `/Users/us/Tools/Development/Calendar_Dev`
- Shared references: `/Users/us/マイドライブ/Tools/Calendar_GD`
- Chat exchange (separate from reference sync): `/Users/us/マイドライブ/Tools/Calendar_Chat`
- Private local data: `/Users/us/Tools/LocalData/Calendar_Local`

Never copy private local data into this repository or the shared-reference folder.

## Cloud / Local boundary

- Work on GitHub-managed code, confirmed specifications, and ordinary tests using synthetic data can be completed in Cloud with access to the required repositories and tools.
- Official synchronization to `Calendar_GD`, `Calendar_Local` and real Trip operations, Mac production updates, and physical-device checks are Local work. Do not copy these resources or credentials into Cloud.
- Keep the existing Mac operation in place and report Cloud validation separately from any remaining Local work. Common procedures continue to follow the current GitHub TDS.

## Start every task here

1. Fetch and read `CODEX_START.md` and its linked rules from the current GitHub `main` of `USXUSX/ToolDevelopmentStandard`, then read `README.md`.
2. Read only the documents linked from `README.md` that are relevant to the task.
3. Treat `/Users/us/マイドライブ/Tools/Calendar_GD` as the one-way reference copy of committed Git source; do not edit it directly or reverse-sync it.
4. Inspect `/Users/us/Tools/LocalData/Calendar_Local` only when the task needs non-shared runtime or sample-input data. Treat its contents as private and do not quote, commit, upload, or log them unless the user explicitly authorizes it.
5. Check `git status` before editing. Preserve unrelated user changes.

Do not scan either external folder broadly without a task-specific reason. Prefer filenames, indexes, and targeted searches.

## Sources of truth

- Code, confirmed specifications, tests, and development history: this Git repository and GitHub.
- Work requests and acceptance criteria: GitHub Issues.
- Review and merge history: GitHub Pull Requests.
- Shared reference copy: `/Users/us/マイドライブ/Tools/Calendar_GD` (committed Git content only; Git remains authoritative).
- Private or machine-local data: `/Users/us/Tools/LocalData/Calendar_Local` (never authoritative for shared behavior).

When sources conflict, stop and identify the conflict. Do not silently overwrite a confirmed repository specification with a reference or local-data file.

## Change rules

- Keep changes small, reversible, and limited to the requested scope.
- Do not modify or migrate the legacy Calendar prototype at `/Users/us/CommonTool/Calendar`.
- Do not publish, deploy, enable external delivery, or change sharing without explicit user approval.
- Do not introduce credentials, personal data, generated caches, or machine-specific runtime files into Git.
- Do not choose an application framework or production architecture until that decision is recorded in `docs/decisions.md`.
- Update tests and confirmed documentation when behavior changes.

## Verification and handoff

- Work initiation, Issue preparation, permissions, validation, review, and completion follow the current GitHub TDS. Preserve the Calendar-specific data and operational boundaries above.
- Temporary visual-review material follows `docs/workflow.md`; neither `Calendar_GD` nor `Calendar_Local` is an independent handoff destination.

Keep this file concise. Put detailed product specifications in `docs/` and add only recurring project-wide guidance here.
