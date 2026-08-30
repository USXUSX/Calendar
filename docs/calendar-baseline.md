# CAL再構築Baseline

## 1. 位置付け

この文書はIssue #46で確定した、CALの責務、主要Entity、データの役割分担、他ツールとの境界を定める現行Baselineである。後続のschema、interface、UI、移行はこのBaselineを前提に個別Issueで決定する。

既存のformal Trip JSON、生成手順、Schema、stable ID、cross-reference validationは、Tripの完全旅程表現とAI再生成方式として新Baselineにも維持し、原則として再利用対象とする。既存のread-only旅程Webは現行実装を理解するために残すが、CAL全体のアプリケーションBaselineではない。旧実装や実データは、このIssueでは変更、移行、削除しない。

## 2. CALの責務

CALは、個人の時間、予定、行うべきことを管理するドメイン基盤である。主要Entityを次の3つとする。

- `Trip`: 旅行というまとまり。期間、参加者、旅行に属する予定等を束ねる。
- `Event`: 日時を持つ予定。旅行中の予定に限らず、通常のスケジュールも表す。
- `Todo`: 人が行うべきこと。必要に応じて`Trip`または`Event`へ関連付けられる。

CALの統一`Schedule / Today`等では、SQLite上の通常`Event`と、formal Trip JSONの`scheduleItem`、`transport`等から投影したTrip由来Eventを、意味ベースの統一Event read modelとして扱う。Trip由来Eventは派生read modelであり、通常のSQLite `Event`として正本複製しない。投影元は`trip_id`とsource itemで追跡する。Issue #52のdomain interface v1では`scheduleItem`と`transport`を投影し、`ordinary:<event-id>`と`trip:<trip-id>:<source-type>:<source-item-id>`を安定したread identityとする。read modelはsource kind、title/summary、開始・終了、visibilityに加え、通常Event IDまたはTrip source情報を返す。transportのtitleはPlace参照をCAL内部で解決する。

各旅行の旅程機能では、最後にAI生成され必要なValidationを通過したformal Trip JSONをauthoritative baseとする。owner画面等で現在有効な旅程として扱う`effective Trip`は、Trip JSONにSQLite上のactive `Direct Override`を適用した派生read modelである。これにより、直接指定のたびにSQLiteとJSONを同時更新せず、二重正本と両者を跨ぐtransactionを避ける。

CALのドメイン用語には`Task`を使用しない。人が行うべきことは`Todo`と呼ぶ。旧JSON schema、サンプル、プロトタイプ実装に残る`tasks`は旧Baselineの互換対象としてのみ扱い、新しいCALモデルへ引き継がない。`Task / TSK`はMac上のJob実行ツールを指し、TSK内の実行単位は`Job`とする。

## 3. ツール間の責務境界

| 対象 | 責務 | CALとの境界 |
| --- | --- | --- |
| CAL | `Trip / Event / Todo`と、それらの関係・状態遷移を管理する | 実データを保持し、意味ベースのread/write境界を提供する |
| FRM | owner向けWeb入口を提供する | CALの物理SQLite schemaを直接操作せず、CALの意味ベースの境界を利用する |
| TSK | Mac上で`Job`を実行するscheduler | CAL全体を同期しない。自動処理が必要な`Event`または`Todo`だけを、将来の明示的な連携境界から`Job`へ接続する |
| ENT | 複数用途で使う取得・蓄積データの基盤 | CALとDBを統合しない。ENTの取得情報をCALへ変換することはできるが、CALデータをENTへ集約することは前提にしない |

FRMのowner向け画面は将来`Today / Schedule / Trips / Todos`を扱える。framework、API方式、CLI、library、local APIの選択はこのBaselineでは固定しない。

## 4. SQLiteとTrip JSONの役割分担

CALはSQLiteとformal Trip JSONのハイブリッド構成を前提とする。どちらも`/Users/us/Tools/LocalData/Calendar_Local`内に置き、Gitや共有参考資料へ実データを置かない。

SQLiteは構造化されたCALの状態を管理する。第一候補の配置先は`/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3`とし、主に次を扱う。

- CAL全体のTrip管理情報
- 通常の`Event`と`Todo`
- `Trip / Event / Todo`間の関係
- `AI Instruction`
- `Direct Override`
- share、visibility等の状態
- その他の構造化されたCAL横断状態

formal Trip JSONは、各旅行について最後にCALが必要なValidationを通して採用したauthoritativeな完全旅程baseである。既存のJSON Schema、stable ID、cross-reference validationを再利用する。AIは更新時にbaseへ対するJSON Patchだけを生成し、CALがmemory copyから次のcomplete candidateを構築する。

1 AI Instructionは登録transaction内で1 generation requestを作る。CALのclaimは同一Tripを直列、別Tripを並列に扱い、Instruction本文、Trip内容、base version/hashを意味境界として返す。CALは返却されたPatchをmemory copyへ適用し、complete candidateをSchema、semantic、cross-reference、Trip ID、active Direct Override、Todoの`trip_item_id`参照まで検証する。採用直前にもbase version/hashが一致する場合だけatomic replacementし、Trip version増加、Instruction applied、request completedを一続きの採用結果にする。

filesystem replaceとSQLite更新の間の停止は一時digest journalで収束する。journalはTrip、request、Instruction、old version/hash、candidate hashを保持する。candidate一致ならversion増加・applied・completedを完了し、old hash一致ならpending・queuedへ戻す。どちらでもなければConflictとして停止する。

正本境界は次のとおりとする。

- 通常のCAL `Event`: SQLite
- CAL `Todo`: SQLite
- Trip管理情報、share / visibility、変更入力等のCAL横断状態: SQLite
- Trip旅程のAI生成base: formal Trip JSON
- ユーザーの旅程への直接指定: SQLite上のactive `Direct Override`

Trip由来Eventを通常のSQLite `Event`として正本化しない。SQLite v1はIssue #50の初期revisionとして保持し、Issue #54の現行complete schemaは`Schemas/calendar-v2.sql`とする。v2はTrip logical version、Instruction base snapshot、generation request queueだけを追加する。実運用DBはまだなくmigration frameworkは導入しない。

3層の役割は維持する。

- `Calendar_Dev`: コード、確定仕様、schema、test、Issue、PR
- `Calendar_GD`: Review、Screenshot、共有参考資料
- `Calendar_Local`: SQLite、formal Trip JSONを含む実データ、runtime data、machine-local data

## 5. 旅程変更の入力経路

旅程の曖昧さや複数箇所に及ぶ調整はAIに交通整理させるが、AIの更新出力はcurrent baseに対するJSON Patchとする。CALだけがcomplete candidateを構築・検証・採用する。

### AI Instruction

ユーザーが自然言語で登録する変更命令。登録と同時にgeneration requestを作り原則即時処理対象にする。「2日目は移動を少なくする」等を扱い、successful adoptionまでは`effective Trip`へ反映しない。

### Direct Override

ユーザーが旅程画面上で登録する具体的な変更。コメント、メモ、店名、時刻等の明示値を扱う。既存のstable IDで対象を識別してSQLiteへactive `Direct Override`として登録し、Trip JSON本体を即時更新せず`effective Trip`へ直ちに反映する。Direct Overrideは現在のJSONへ一度適用して自動消費・削除する入力ではない。次回以降のAI再生成にも渡し、ユーザーが直接指定した内容が失われないようにする。同一`trip_id + source_item_id + field_path`はSQLite上の1行を現在指定として更新し、解除時は`active = 0`にする。AI再生成成功後も自動でinactive化しない。candidateとの整合確認、AI Instructionとの競合UI、hard / soft分類は後続Issueで決定する。

初期Baselineではhard/soft等へ細分化せず、`AI Instruction`と`Direct Override`を区別する。

```text
AI Instruction + CAL-owned base Trip/version/hash
  -> AI / WorkがJSON Patch生成
  -> CALがmemory copyへ適用してcomplete candidate構築
  -> complete Validation + base再確認 + atomic adoption
```

Patch適用後candidateは既存Schema、stable ID、cross-reference validationをすべて通過した場合だけcurrentへ採用する。stale version/hashはPatch非適用でrequestをqueuedへ戻し、Validation失敗はcurrentを維持する。不完全JSONをcurrentとして表示しない。active Overrideと同じ`source_item_id + field_path`を変更するPatchは、AI Instructionの効果が隠れる明白な競合として採用前に拒否する。active Overrideを適用したeffective Tripも再Validationし、存在しないtargetやTodo参照切れは拒否する。

AI Instructionは`pending`、requestは`queued / processing / completed / cancelled`を持つ。Patch生成失敗はrelease、staleは自動requeueし、Instructionをpendingに保つ。successful adoption時だけInstructionをapplied、requestをcompletedにする。

CAL-owned one-shot workerは1 runで原則1 requestだけを処理する。起動時に未完了のadoption journalを回復し、requestがなければno-opで正常終了する。generatorはCAL semantic claim payloadだけを受け取りJSON Patchだけを返し、SQLite table、Trip file path、採用処理を知らない。generator起動失敗、timeout、JSON不正はrequestをqueuedへreleaseする。staleは既存domain境界でqueuedへ戻す。Schema不適合やsemantic conflictは同じ入力の無限再試行を避けるためrequestを停止し、Instructionはpendingのまま人の確認対象として残す。

TSKはこのone-shot commandをJobとして起動するだけで、CALのschema、Trip JSON配置、request stateを操作しない。provider接続、認証、model選択、通常ChatGPT Workの外部自動起動可否はCAL coreおよびこのworkerの前提にしない。

最初のprovider implementationは外部generator commandとして分離したOpenAI Responses API adapterである。semantic claimからInstructionとcomplete base Tripを送り、成功時はPatch配列だけをworkerへ返す。OpenAI固有のendpoint、credential、model、HTTP処理はCAL core / workerへ入れない。API段階のStructured Outputsとadapter shape検証は補助であり、CAL domainのcomplete candidate Validationとatomic adoptionが最終authorityである。

## 6. 統一Event read modelと更新command境界

統一`Schedule / Today`等のEvent read modelは、次の2ソースを意味ベースで合成する。

- SQLiteを正本とする通常Event
- formal Trip JSONから投影するTrip由来Event

同じ画面に表示してもsourceを保持し、更新commandを次の正本へ振り分ける。

- 通常Eventを編集する: SQLite `Event`を更新する。
- Trip由来Eventを直接編集する: stable IDを対象とする`Direct Override`を登録する。
- Trip由来Eventへの自然言語の変更意図を登録する: `AI Instruction`を登録する。

Trip由来Eventを通常のSQLite `Event`へ変換して更新しない。

## 7. ownerデータとparticipant向けread model

CALのSQLite、Trip JSON、owner向けドメイン境界は、ownerの完全なデータを扱う。旅行参加者へCAL本体、SQLite、owner用Trip JSON、owner向けread/write境界を直接公開しない。

participant向け共有は、`effective Trip`とSQLite上のvisibility / share状態から共有対象だけを抽出したread modelを生成する境界で行う。Trip JSONファイル、SQLite、Direct Override、AI Instructionをparticipantへ直接公開しない。

- 初期visibilityは`owner`と`participants`を基本とする。
- 主な共有対象は`Trip`と`Event`とする。
- `Todo`は初期の必須共有対象にしないが、将来の明示的な共有を妨げない。
- participant向けread modelは読み取り専用で、owner専用フィールドや未共有Entityを含めない。
- owner側の更新後にread modelを再生成できる一方向の派生物とし、participant側の値を正本へ逆流させない。
- 共有対象の選択規則、URL、認証、公開基盤、更新頻度は後続Issueで確定する。

この境界は将来の共有を可能にするための仕様であり、このIssueでは外部公開を開始しない。

## 8. 旧Baselineとの関係

### Supersedeする内容

- Calendar自身のread-only旅程WebをCALの中心とする方針
- 旅程管理だけをCAL全体の主目的とする方針
- 旅行JSONだけでCAL全体の`Trip / Event / Todo`と横断状態を管理する方針
- 旅行を中心に`Day / ScheduleItem / Transport / Preparation`等からCAL全体を構成する前提

### 残す内容

- 各旅行をformalな完全Trip JSONで表す基本方式
- AIがJSON Patchを生成し、CALが次版complete Trip JSONを構築する方式
- JSON Schema、stable ID、cross-reference validation、予定と実績を分ける考え方
- 既存のSchema、validator、合成サンプル、旅行JSON生成・運用文書は、再利用対象かつ現行実装の記録として残す。
- read-only Webの実装は移行・再利用判断の資料として残す。
- 既存旅程データと旧実装は、新Baselineへの移行または再利用を決める後続Issueまで変更しない。

旧資料にある個別の表示仕様や旅行詳細項目は、自動的に新Baselineへ継承しない。後続Issueで採用したものだけを新しい確定仕様へ昇格する。

## 9. 後続Issueへの分割

1. `Trip / Event / Todo`と変更入力のSQLite schema、状態遷移、参照制約
2. `AI Instruction / Direct Override`のライフサイクル、競合・解除・適用済み状態、hard / soft分類
3. unified Event projectionと`effective Trip`合成を含む、CALの意味ベースのdomain interface（Issue #52でv1実装）
4. AI Instruction即時Patch pipeline、candidate採用atomicityと最小recovery（Issue #54で実装）
5. 既存Trip JSON、Schema、validatorの再利用範囲と必要な非破壊的移行
6. FRM owner向け`Today / Schedule / Trips / Todos` read modelと画面
7. FRMからCALを更新するcommand境界、競合、validation
8. formal Trip JSONを表示・変更するowner向け旅行UI
9. participant向けread modelの投影規則、共有範囲、認証、公開基盤
10. Reminder、繰返し`Event`、AI更新、必要箇所だけのTSK `Job`連携
11. ENT取得データをCALへ変換する連携契約
12. 旧read-only prototypeの再利用判断と非破壊的整理

各Issueは、このBaselineで未確定とした方式を必要な範囲だけDecision化し、実装、移行、公開を混在させない。
