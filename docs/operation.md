# Calendar Trip JSON現行運用手順

> **Status:** この手順は現行read-only旅程Webと既存Trip JSONに適用する。Issue #54のCAL側Patch pipelineはGit管理下で実装されているが、実運用DB、FRM、TSK / Work接続は未実装である。

## 1. 原則

Calendar は正式仕様の旅行 JSON を読み取り、見やすく表示する。旧形式 JSON の互換変換は行わない。表示できない場合は、元の JSON を正式仕様に合わせて修正または完全再生成する。

実データは `/Users/us/Tools/LocalData/Calendar_Local/trips/` にだけ置き、Git リポジトリや Google Driveへコピー、コミット、アップロードしない。

SQLiteの現行revisionは`Schemas/calendar-v2.sql`である。v1は初期revisionとして保持する。開発用の空DBは明示した一時pathに`python3 scripts/init_calendar_db.py <path>`で初期化できる。各接続は`PRAGMA foreign_keys = ON`を有効にする。このIssueでは`Calendar_Local/db/calendar.sqlite3`を作成・変更せず、実データ移行も行わない。

CAL利用側は`CalendarDomain`へDB pathとTrip rootを明示して接続し、SQLite tableやTrip file pathを扱わない。Instruction登録は同じtransactionでrequestをqueuedにし、claimはInstruction本文、Trip内容、base version/hashを返す。workerはJSON Patchだけをsubmitし、complete candidateの構築・Validation・採用はCAL内部で行う。

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

1. AI Instructionを登録し、同一transactionでgeneration requestをqueuedにする。
2. workerがrequestをclaimし、CALからInstruction、Trip内容、base version/hashを受け取る。同一Tripの次requestは先行request完了までclaimしない。
3. AI / Workはbaseに対する`add` / `remove` / `replace` JSON Patchだけを返す。
4. CALはbase version/hashを再確認し、memory copyへPatchを適用する。staleならcurrentを変更せずInstruction pendingのままrequestをqueuedへ戻す。
5. CALがcomplete candidate全体のSchema、semantic/cross-reference、Trip ID、Override適用後effective Trip、Todo参照を検証し、採用直前にもbaseを確認する。
6. complete candidateだけをatomic replaceし、Trip versionを増加、Instructionをapplied、requestをcompletedにする。active Overrideは維持する。

AIはcurrent Trip JSONを直接変更せず、complete Trip JSONを標準更新interfaceへ返さない。replace後・SQLite更新前に停止した場合、`recover_trip_adoption()`がrequest/instruction、old version/hash、candidate hashを照合する。candidate一致ならversion増加・applied・completedを完了し、old hash一致ならpending・queuedへ戻す。どちらでもなければConflictとして自動収束しない。

## 5. 新規旅行

1. Chat に旅行計画資料、`Schemas/trip.schema.json`、`docs/trip-json-generation.md`の生成指示を渡し、完全 JSON の作成を依頼する。
2. 生成JSONを`trips/`以外の一時作業場所へ保存し、`python3 scripts/validate_trip.py <生成JSON>`を実行する。
3. エラーがあればエラーパスだけをChatへ返し、修正済みの完全JSONを再生成して再検証する。部分JSONやCalendar側の補正では直さない。
4. 検証成功後、JSONの内容、安定ID、参照関係を確認する。
5. ファイル名を`id`と一致させて`Calendar_Local/trips/<trip-id>.json`へ配置し、Calendarの一覧と5画面を確認する。

この新規旅行作成手順は既存Tripの標準更新経路には使わない。既存TripはAI InstructionからJSON Patchを生成し、CALがcomplete candidateを構築する。

実旅行ではSchema成功後に、予定・移動・Placeの重複、候補Placeの欠落、Bookingの対象参照と対象日も確認する。不足はまず完全JSONの再生成で直し、JSONで表現できない表示上の必要性が確認できた場合だけUI改善を別Issueにする。
