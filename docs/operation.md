# Calendar 実運用手順

## 1. 原則

Calendar は正式仕様の旅行 JSON を読み取り、見やすく表示する。旧形式 JSON の互換変換は行わない。表示できない場合は、元の JSON を正式仕様に合わせて修正または完全再生成する。

実データは `/Users/us/Tools/LocalData/Calendar_Local/trips/` にだけ置き、Git リポジトリや Google Driveへコピー、コミット、アップロードしない。

## 2. ファイル配置

旅行ごとに1つの完全 JSON を置く。ファイル名は変更しない `trip.id` と一致させる。

```text
Calendar_Local/
  trips/
    <trip-id>.json
```

候補、履歴、差分 JSON を Calendar 専用の恒久データとして管理しない。必要な変更は Chat に依頼し、返された完全 JSON を人が確認してから対象ファイルと置き換える。置換前の一時バックアップが必要な場合は、通常のファイル操作や端末のバックアップを使う。

## 3. 閲覧

1. `python3 scripts/validate_trip.py Calendar_Local/trips/<trip-id>.json`を実行し、正式スキーマと参照整合性を確認する。ファイル名と`id`も一致させる。
2. リポジトリ直下で `python3 scripts/serve_calendar.py` を実行する。
3. `http://127.0.0.1:4174/Sources/web/` を開く。

サーバーはブラウザから Git 外の実データを読めるようにする最小限の読み取り専用入口である。`trips/*.json` の一覧と、指定された旅行 JSON だけを返し、書き込みは行わない。静的レビュー環境ではコミット済みの合成 JSON を表示する。

## 4. 更新

1. Calendar 上のチェック、候補選択、コメントを更新材料として確認する。
2. 対象の完全 JSON と更新材料を Chat に渡し、正式仕様に従う次版の完全 JSON を依頼する。
3. 返された完全 JSON の全体、`id`、参照関係、表示を確認する。
4. 問題がなければ対象の `<trip-id>.json` を置き換える。問題があれば JSON を修正または再生成し、現在のファイルは置き換えない。

Calendar は JSON の直接編集、旧形式からの自動変換、自動採用、自動復旧を行わない。画面上の一時状態は採用済み JSON の内容ではない。

## 5. 新規旅行

1. Chat に旅行情報と正式仕様を渡し、完全 JSON の作成を依頼する。
2. JSON の構造、安定 ID、参照関係、内容を確認する。
3. `Calendar_Local/trips/<trip-id>.json` として保存し、Calendar で表示を確認する。
