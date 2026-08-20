# Project structure

## Goal

Calendar uses one project name across three locations so Codex can resolve source, shared references, and private local data from a stable rule.

## Boundaries

### Development

`/Users/us/Tools/Development/Calendar_Dev` is the Git repository and the canonical location for source code, confirmed specifications, tests, and development history.

### Google Drive

`/Users/us/Tools/GoogleDrive/Calendar_GD` holds reference documents, screenshots, and handoff material. Files here are inputs for review, not confirmed specifications. Promote an accepted requirement into `docs/` through a reviewed Git change.

### Local data

`/Users/us/Tools/LocalData/Calendar_Local` holds private or machine-specific data. It is outside Git and Google Drive. Code may read it through documented configuration later, but must not assume sample production data is safe to share.

The role READMEs in `Calendar_GD` and `Calendar_Local` are generated from `templates/folder-readmes/` by `scripts/sync_folder_readmes.sh`. Edit the Git templates, then synchronize outward; do not maintain independent copies in those external folders.

## Discovery rule

The repository root is the only folder a user needs to open in Codex. `AGENTS.md` provides the two external locations and the inspection rules. Each external folder contains a small index explaining its role.

## Legacy boundary

`/Users/us/CommonTool/Calendar` is a separate legacy prototype. This new repository must not edit, move, import, or depend on it unless a future migration is explicitly approved.
