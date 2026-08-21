# 実機レビュー用 Pages

固定確認URLは `https://usxusx.github.io/Calendar/` です。公開可能な合成データだけを表示し、認証や秘密情報は使用しません。

## 最新レビュー版を反映する

1. GitHub Actions の **Deploy review Pages** を開く。
2. **Run workflow** で、実機確認するPRのブランチ名またはコミットSHAを `review_ref` に指定する。
3. workflowの完了後、固定確認URLを開く。

配信対象は `Sources/web` と `Samples/synthetic-trip.json` だけです。通常の `Validate` とは独立しており、PRごとのURLは作りません。再実行すると同じ固定URLが指定refの内容で置き換わります。

Issue #17 の初回導入時だけ、workflowブランチのpushを起点に `codex/issue-15-ui-density`（PR #16）を配信します。導入後は上記の手動実行を使います。
