# Calendar Trip JSON現行運用手順

> **Status:** この手順は現行read-only旅程Webと既存Trip JSONに適用する。Issue #52のCAL domain interface v1とIssue #54のcandidate採用境界はGit管理下で実装されているが、実運用DB、FRM接続、AI生成連携は未実装である。新しい統合運用は[`calendar-baseline.md`](calendar-baseline.md)と後続Issueで定める。

## 1. 原則

Calendar は正式仕様の旅行 JSON を読み取り、見やすく表示する。旧形式 JSON の互換変換は行わない。表示できない場合は、元の JSON を正式仕様に合わせて修正または完全再生成する。

実データは `/Users/us/Tools/LocalData/Calendar_Local/trips/` にだけ置き、Git リポジトリや Google Driveへコピー、コミット、アップロードしない。

SQLite v1のGit管理上の正本は`Schemas/calendar-v1.sql`である。開発用の空DBは明示した一時pathに`python3 scripts/init_calendar_db.py <path>`で初期化できる。各接続は`PRAGMA foreign_keys = ON`を有効にする。このIssueでは`Calendar_Local/db/calendar.sqlite3`を作成・変更せず、実データ移行も行わない。

CALを利用する将来のFRM adapter等は`Sources.calendar_domain.CalendarDomain`へDB pathとTrip rootを明示して接続する。SQLite tableを直接query/updateせず、Trip JSONのcurrent pathや内部collection、atomic replacement手順を解釈しない。v1のTrip registryは規定rootの`trips/<trip-id>.json`を検証して登録する。candidate採用は`adopt_trip_candidate(trip_id, candidate, instruction_ids)`へcomplete JSONと、その生成に実際に使ったpending Instruction IDだけを渡す。

Domain writeは1 commandを1 SQLite transactionとして扱い、失敗時にpartial updateを残さない。Direct OverrideはSQLiteへ保存するが、effective Tripへの適用はメモリ上だけであり、authoritative Trip JSONを変更しない。

## 2. ファイル配置

旅行ごとに1つの完全 JSON を置く。ファイル名は変更しない `trip.id` と一致させる。

```text
Calendar_Local/
  trips/
    <trip-id>.json
```

候補、履歴、差分 JSON を Calendar 専用の恒久データとして管理しない。domain採用処理はprivate Trip rootの`.adoption/`だけにstagingとdigest journalを一時作成し、成功または回復収束後に削除する。これはpermanent historyではない。

## 3. 閲覧

1. `python3 scripts/validate_trip.py Calendar_Local/trips/<trip-id>.json`を実行し、正式スキーマと参照整合性を確認する。ファイル名と`id`も一致させる。
2. リポジトリ直下で `python3 scripts/serve_calendar.py` を実行する。
3. `http://127.0.0.1:4174/Sources/web/` を開く。

サーバーはブラウザから Git 外の実データを読めるようにする最小限の読み取り専用入口である。`trips/*.json` の一覧と、指定された旅行 JSON だけを返し、書き込みは行わない。静的レビュー環境ではコミット済みの合成 JSON を表示する。

## 4. 更新

1. Calendar 上のチェック、候補選択、コメントを更新材料として確認する。
2. 対象の完全 JSON と更新材料を Chat に渡し、正式仕様に従う次版の完全 JSON を依頼する。
3. 返された完全 JSON の全体、`id`、参照関係、表示を確認する。
4. 問題がなければCAL domainのcandidate採用境界へcomplete candidateと対象Instruction IDを渡す。Schema、semantic、cross-reference、Trip ID、registry、Override適用後のeffective Trip、Todo item参照をすべて確認した後だけ、staging済みbytesをsame-filesystem atomic replacementでcurrentへ切り替える。問題があればJSON を修正または再生成し、currentは置き換えない。
5. 採用成功時だけ指定pending Instructionが`applied`になる。別のpending Instructionとactive Overrideは維持される。

Calendar は JSON の直接編集、旧形式からの自動変換、AI candidate生成を行わない。画面上の一時状態は採用済み JSON の内容ではない。replace後・SQLite更新前に停止した場合は、次の`adopt_trip_candidate()`または明示的な`recover_trip_adoption()`がjournalとcurrent digestを比較する。candidateへ切替済みならInstruction更新を完了し、旧currentならInstructionをpendingのまま未採用としてcleanupする。どちらのdigestでもなければConflictとして停止する。

## 5. 新規旅行

1. Chat に旅行計画資料、`Schemas/trip.schema.json`、`docs/trip-json-generation.md`の生成指示を渡し、完全 JSON の作成を依頼する。
2. 生成JSONを`trips/`以外の一時作業場所へ保存し、`python3 scripts/validate_trip.py <生成JSON>`を実行する。
3. エラーがあればエラーパスだけをChatへ返し、修正済みの完全JSONを再生成して再検証する。部分JSONやCalendar側の補正では直さない。
4. 検証成功後、JSONの内容、安定ID、参照関係を確認する。
5. ファイル名を`id`と一致させて`Calendar_Local/trips/<trip-id>.json`へ配置し、Calendarの一覧と5画面を確認する。

既存旅行を変更する場合も、現在の完全JSONと変更依頼をChatへ渡し、既存IDと変更対象外の内容を維持した次版の完全JSONを生成する。同じ検証と表示確認を通過してから置き換える。

実旅行ではSchema成功後に、予定・移動・Placeの重複、候補Placeの欠落、Bookingの対象参照と対象日も確認する。不足はまず完全JSONの再生成で直し、JSONで表現できない表示上の必要性が確認できた場合だけUI改善を別Issueにする。
