# Calendar project guidance

## Purpose

This repository is the canonical home for Calendar source code, confirmed specifications, tests, and GitHub Issue/PR work.

## Project locations

- Repository: `/Users/us/Tools/Development/Calendar`
- Shared references: `/Users/us/Tools/GoogleDrive/Calendar`
- Private local data: `/Users/us/Tools/LocalData/Calendar`

Never copy private local data into this repository or the shared-reference folder.

## Start every task here

1. Read `README.md`.
2. Read only the documents linked from `README.md` that are relevant to the task.
3. Inspect `/Users/us/Tools/GoogleDrive/Calendar` only when the task needs reference material, screenshots, or handoff documents.
4. Inspect `/Users/us/Tools/LocalData/Calendar` only when the task needs non-shared runtime or sample-input data. Treat its contents as private and do not quote, commit, upload, or log them unless the user explicitly authorizes it.
5. Check `git status` before editing. Preserve unrelated user changes.

Do not scan either external folder broadly without a task-specific reason. Prefer filenames, indexes, and targeted searches.

## Sources of truth

- Code, confirmed specifications, tests, and development history: this Git repository and GitHub.
- Work requests and acceptance criteria: GitHub Issues.
- Review and merge history: GitHub Pull Requests.
- Reference material and screenshots: `/Users/us/Tools/GoogleDrive/Calendar` (not authoritative unless promoted into a confirmed specification in this repository).
- Private or machine-local data: `/Users/us/Tools/LocalData/Calendar` (never authoritative for shared behavior).

When sources conflict, stop and identify the conflict. Do not silently overwrite a confirmed repository specification with a reference or local-data file.

## Change rules

- Keep changes small, reversible, and limited to the requested scope.
- Do not modify or migrate the legacy Calendar prototype at `/Users/us/CommonTool/Calendar`.
- Do not publish, deploy, enable external delivery, or change sharing without explicit user approval.
- Do not introduce credentials, personal data, generated caches, or machine-specific runtime files into Git.
- Do not choose an application framework or production architecture until that decision is recorded in `docs/decisions.md`.
- Update tests and confirmed documentation when behavior changes.

## Verification and handoff

- Run the narrowest relevant checks first; run the full test suite when one exists and the change warrants it.
- Report changed files, checks performed, and any remaining uncertainty.
- Future delivery flow: Chat discussion -> GitHub Issue -> Codex implementation -> tests -> review -> Pull Request.

Keep this file concise. Put detailed product specifications in `docs/` and add only recurring project-wide guidance here.
