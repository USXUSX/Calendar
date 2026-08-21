# Calendar project guidance

## Purpose

This repository is the canonical home for Calendar source code, confirmed specifications, tests, and GitHub Issue/PR work.

## Project locations

- Repository: `/Users/us/Tools/Development/Calendar_Dev`
- Shared references: `/Users/us/Tools/GoogleDrive/Calendar_GD`
- Private local data: `/Users/us/Tools/LocalData/Calendar_Local`

Never copy private local data into this repository or the shared-reference folder.

## Start every task here

1. Read `README.md`.
2. Read only the documents linked from `README.md` that are relevant to the task.
3. Inspect `/Users/us/Tools/GoogleDrive/Calendar_GD` only when the task needs reference material, screenshots, or handoff documents.
4. Inspect `/Users/us/Tools/LocalData/Calendar_Local` only when the task needs non-shared runtime or sample-input data. Treat its contents as private and do not quote, commit, upload, or log them unless the user explicitly authorizes it.
5. Check `git status` before editing. Preserve unrelated user changes.

Do not scan either external folder broadly without a task-specific reason. Prefer filenames, indexes, and targeted searches.

## Sources of truth

- Code, confirmed specifications, tests, and development history: this Git repository and GitHub.
- Work requests and acceptance criteria: GitHub Issues.
- Review and merge history: GitHub Pull Requests.
- Reference material and screenshots: `/Users/us/Tools/GoogleDrive/Calendar_GD` (not authoritative unless promoted into a confirmed specification in this repository).
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

- Follow the common tool-development workflow at `/Users/us/Tools/Development/ToolDevelopmentStandard/TOOL_DEVELOPMENT_WORKFLOW.md` unless this file sets a stricter Calendar-specific rule.
- Run the narrowest relevant checks first; run the full test suite when one exists and the change warrants it.
- Report changed files, checks performed, and any remaining uncertainty.
- For visual review, save screenshots under `/Users/us/Tools/GoogleDrive/Calendar_GD/Review/PR-<number>/`; never commit them or place them in `Calendar_Local` for handoff.
- Record actionable Chat review findings directly in the Pull Request, then update and re-verify the same Pull Request.
- Delivery flow: Chat discussion -> GitHub Issue -> Codex implementation -> tests -> Draft Pull Request -> Chat review -> PR comments -> Codex fixes -> re-review -> human-approved merge.

Keep this file concise. Put detailed product specifications in `docs/` and add only recurring project-wide guidance here.
