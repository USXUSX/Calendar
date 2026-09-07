# Development workflow

着手・Issue整備・許可・Validation・Review・完了は、GitHub `USXUSX/ToolDevelopmentStandard` の現行mainにある `CODEX_START.md` と参照先に従う。Calendar固有のデータ・運用境界は `../AGENTS.md` を参照する。

画面Reviewが必要な場合だけ、画像等をGit管理外の一時場所（例: `/tmp`）へ用意し、usが確認できるリンクを示す。画像をGitへコミットせず、`Calendar_GD` や `Calendar_Local` へ受け渡し目的で追加しない。共有が必要ならTDSの共有コピーとは別の許可された場所を使う。

Git正本のremoteは `USXUSX/Calendar`。公式同期はmerge済みのコミットを `git archive` で一時展開し、`Calendar_GD` へ一方向複製して一致を確認する。共有READMEもGit正本のREADMEを使う。同期以外の独自ファイルを共有コピーへ置かない。
