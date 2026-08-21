# Development workflow

共通手順は `/Users/us/Tools/Development/ToolDevelopmentStandard/TOOL_DEVELOPMENT_WORKFLOW.md` に従う。

Calendarでは、画面レビュー用スクリーンショットを次へ保存する。

`/Users/us/Tools/GoogleDrive/Calendar_GD/Review/PR-<番号>/`

画像はGitへコミットせず、`Calendar_Local` も受け渡しには使わない。レビュー指摘はGitHub PRへ直接記録し、Codexは同じPRを更新する。

Calendarの基本フローは次のとおり。

1. Discuss and clarify an idea in Chat.
2. Create a GitHub Issue containing scope and acceptance criteria.
3. Let Codex inspect the repository guidance and implement a focused change.
4. Run relevant automated and manual checks.
5. Open or update a Draft Pull Request linked to the Issue.
6. When visual review is needed, save screenshots in the PR-specific Google Drive review folder.
7. Review the diff, test evidence, and screenshots in Chat; record required fixes in the Pull Request.
8. Let Codex address the review comments in the same Pull Request and rerun the checks.
9. Re-review and merge only after human approval.

The repository remote is `USXUSX/Calendar`. Do not create Issues, branches, or Pull Requests without user authorization.
