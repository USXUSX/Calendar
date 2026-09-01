# Calendar Trip JSON現行運用手順

> **Status:** この手順は現行旅程Webと既存Trip JSONに適用する。CAL側Direct Override、Patch pipeline、one-shot workerはGit管理下で実装されているが、実運用DB、FRM、TSK接続、credential配置、model選択は未実施である。

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
2. 閲覧だけならリポジトリ直下で `python3 scripts/serve_calendar.py` を実行する。直接編集を有効にする場合は、初期化・Trip登録済みの明示DBを指定して `python3 scripts/serve_calendar.py --db <explicit-db>` を実行する。
3. `http://127.0.0.1:4174/Sources/web/` を開く。

サーバーはブラウザからGit外の実データをCAL意味境界経由で扱うloopback-only入口である。DB未指定時はread-only、DB指定時の直接編集だけは複数fieldを一commandとしてValidationし、SQLiteのDirect Overrideへall-or-nothingで保存する。Trip JSONは変更しない。静的レビュー環境ではコミット済みの合成JSONを表示する。

## 4. 更新

1. AI Instructionを登録し、同一transactionでgeneration requestをqueuedにする。
2. workerがrequestをclaimし、CALからInstruction、Trip内容、base version/hashを受け取る。同一Tripの次requestは先行request完了までclaimしない。
3. AI / Workはbaseに対する`add` / `remove` / `replace` JSON Patchだけを返す。
4. CALはbase version/hashを再確認し、memory copyへPatchを適用する。staleならcurrentを変更せずInstruction pendingのままrequestをqueuedへ戻す。
5. CALがcomplete candidate全体のSchema、semantic/cross-reference、Trip ID、Override適用後effective Trip、Todo参照を検証し、採用直前にもbaseを確認する。
6. complete candidateだけをatomic replaceし、Trip versionを増加、Instructionをapplied、requestをcompletedにする。active Overrideは維持する。

one-shot workerは起動時に未完了adoptionを回復し、1 runで最大1 requestを処理する。requestなしは正常なno-opである。外部generatorはshell文字列ではなくargvで明示指定し、stdinでsemantic claim payloadを受け、stdoutへJSON Patch配列を返す。失敗、timeout、JSON不正はreleaseして再処理可能にし、staleはrequeueする。Validationまたはsemantic conflictはrequestを停止してInstruction pendingを維持し、人の確認が必要な結果として返す。

TSKへ登録する後続運用では `python3 scripts/run_generation_worker.py --db <explicit-db> --trip-root <explicit-root> -- <generator-argv...>` をone-shot Jobとして呼ぶ。TSKはCAL内部tableやTrip fileを扱わない。このIssueでは実運用interval、Task_Local、launchd、provider認証を設定しない。

OpenAI adapterは `scripts/generate_openai_patch.py --model <model-id>` として外部generator argvへ指定できる。stdinのsemantic claimをResponses APIへ渡し、成功時stdoutにはPatch配列だけを出す。API keyは`OPENAI_API_KEY`、modelは`--model`または`OPENAI_MODEL`から取得し、secretを引数、stdout、Git、文書へ置かない。API/network/timeout/refusal/incomplete/parse/shape failureはstderrへ値を含まない診断を出してnon-zero終了し、workerがrequestをreleaseする。

Responses APIではtoolを有効化せず、`store: false`とStructured Outputsを使う。Patchの`value`は任意JSON型でremove時は存在しないためAPI schemaはnon-strictとし、adapterの最小shape検証とCALのJSON Pointer、Trip Schema、semantic、conflict、atomic adoptionを最終authorityとする。通常testはmock transportのみで、実API smoke test、credential配置、課金、実運用model決定は後続運用Issueで明示的に扱う。

AIはcurrent Trip JSONを直接変更せず、complete Trip JSONを標準更新interfaceへ返さない。replace後・SQLite更新前に停止した場合、`recover_trip_adoption()`がrequest/instruction、old version/hash、candidate hashを照合する。candidate一致ならversion増加・applied・completedを完了し、old hash一致ならpending・queuedへ戻す。どちらでもなければConflictとして自動収束しない。

## 5. 新規旅行

1. Chat に旅行計画資料、`Schemas/trip.schema.json`、`docs/trip-json-generation.md`の生成指示を渡し、完全 JSON の作成を依頼する。
2. 生成JSONを`trips/`以外の一時作業場所へ保存し、`python3 scripts/validate_trip.py <生成JSON>`を実行する。
3. エラーがあればエラーパスだけをChatへ返し、修正済みの完全JSONを再生成して再検証する。部分JSONやCalendar側の補正では直さない。
4. 検証成功後、JSONの内容、安定ID、参照関係を確認する。
5. ファイル名を`id`と一致させて`Calendar_Local/trips/<trip-id>.json`へ配置し、Calendarの一覧と5画面を確認する。

この新規旅行作成手順は既存Tripの標準更新経路には使わない。既存TripはAI InstructionからJSON Patchを生成し、CALがcomplete candidateを構築する。

実旅行ではSchema成功後に、予定・移動・Placeの重複、候補Placeの欠落、Bookingの対象参照と対象日も確認する。不足はまず完全JSONの再生成で直し、JSONで表現できない表示上の必要性が確認できた場合だけUI改善を別Issueにする。
