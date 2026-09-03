# 旅程詳細表示・更新契約

> **Status:** Issue #64 Goal 1 / Phase 2で確定。Phase 1の
> [`trip-detail-ui.md`](trip-detail-ui.md) を構成するCAL側の意味境界である。

## 正本と表示モデル

旅程詳細表示モデルは、formal Trip JSONへactive Direct Overrideを適用した
`effective Trip`から毎回派生する。表示モデル自体を保存せず、SQLiteやTrip JSONと
並ぶ正本にしない。FRM等の画面は物理schemaやTrip JSON配置を参照せず、この意味境界を
利用する。

| UI情報 | 取得元・導出 |
| --- | --- |
| 日付、主題、移動概要 | `Day.date / title / routeSummary` |
| 時刻 | `TimeSpec`。`undecided`は「未定」、`range`は開始–終了 |
| カテゴリー | `ScheduleItem.category`。移動は`transport`として派生 |
| 本文、場所link | `action`と`Place`参照。移動は出発地・到着地から派生 |
| 通常コメント | `ScheduleItem.summary` |
| 重要コメント | 対象PlaceまたはTransportに紐づく`Booking.notes`。重要性を推測して`details`を昇格しない |
| 補足事実 | `ScheduleItem.details`。重要コメントとは別に保持する |
| 天気 | Trip正本にはない。取得側が日ID単位のContextとして明示的に渡し、未取得・失敗時は`null` |
| カテゴリーicon | categoryから安定した意味keyへ変換する。具体iconはUI実装時に決める |

`scheduleItem`と`transport`の状態はTrip内容に保持する明示値
`confirmed / tentative / undecided`をそのまま返す。時刻、場所、候補数から導出せず、
それらの編集でも自動変更しない。候補が複数あれば`has_candidates`を独立して返し、
状態を上書きしない。

`候補あり`と候補一覧は`candidatePlaceIds`から導出する。採用済みの選択は`selection`として
区別し、未送信の`OK / NG`をそこへ書き込まない。

## 未送信入力

候補追加、`OK / NG`、予定単位AI指示は採用済みTripではない。画面または上位applicationが
編集sessionの一時状態として保持し、表示モデルへ明示的に渡す。画面を保存せず閉じる場合は
破棄し、送信時だけ次のCAL commandへ変換する。再起動を跨ぐdraft保存が必要になった場合は、
保存期間・取消・競合を別Issueで決める。

- `OK / NG`: `trip_id + source_item_id + place_id`を対象とする候補判断入力。採用済み
  `PlaceSelection.selection`を直接変更しない。
- 候補追加: 対象予定とPlace候補を含む局所更新入力。候補を正本へ加える処理と採否判断を分ける。
- 予定単位AI指示: `trip_item_local_update`として対象type・stable ID・現在対象値・指示を渡し、
  CALが許可した意味フィールド変更だけを結果とする。

## 更新境界

編集画面の具体値は、既存の意味ベースcommandへ対応付ける。

| 編集値 | Trip由来予定のcommand |
| --- | --- |
| 状態 | 対象stable IDの`/status`へのDirect Override |
| 開始・終了・時刻状態 | 対象stable IDの`/time/start`、`/time/end`、`/time/mode`へのDirect Override |
| 予定本文 | `/action`へのDirect Override |
| 通常コメント | `/summary`へのDirect Override |
| 候補と判断 | 上記の未送信入力。`selection`への即時Direct Overrideにはしない |

通常の局所AI更新は、直接編集と同じ対象stable ID・意味フィールド更新境界へ収束させる。
返却値は対象内の`semantic_field_changes`とし、CALが対象、許可field、schema、effective Tripを
検証してからDirect Override相当の局所結果として反映する。通常局所更新を既存の
`generation_requests`へ投入してcomplete Trip candidateを採用する経路にはしない。

新規Trip作成はbaseを持たないため、完全Trip JSONを生成・Schema / semantic validationして
初回採用する独立経路とする。既存Tripの初期化、Day構成や複数対象の関係を大きく組み替える
全体再生成だけが、CAL-owned base/version/hash、JSON Patch、complete candidate Validation、
atomic adoptionを使う。provider、model、credential、AIGはどちらのCAL契約にも含めない。

現行schemaは、Dayと順序、予定のPlace候補・選択、Placeの名前・住所・緯度経度・URL、
Transportの手段・出発地・到着地をstable IDで結べるため、Goal 2で日別の地点と移動を
派生するmap-readinessを満たす。座標が`null`のPlaceは地図点から除外可能であり、地図provider、
route生成、navigation連携はGoal 2で決め、地図用の別正本は作らない。

## Phase 3の直接編集契約

表示モデルの`direct_edit_paths`を使い、`scheduleItem`はstatus、時刻、予定本文、通常コメント、
`transport`はstatusと時刻を一つの意味commandへ渡す。CALはcomplete effective Tripを
Schema・semantic Validationしてから一transactionでDirect Overrideへ反映し、失敗時は
何も部分反映しない。保存後はeffective Tripから再表示する。候補判断と局所AI executorは
直接編集を置き換えず、Phase 4以降でこの同じ意味境界へ接続する。

## Phase 4のWorking Trip保存境界

Working Tripはauthoritative TripやDirect Overrideを書き換えず、SQLite上へTripごと1行の
JSON objectとして最新状態だけを保存する。初回保存時に、その時点のTrip versionと
effective TripのSHA-256を`base_effective_revision`として固定する。後続のWorking編集は
stateだけを置き換え、このrevisionを自動更新しない。

読取時には現在のeffective revisionも計算し、差があれば`stale`を返す。staleでもWorkingの
表示、読取、上書きは継続できる。将来の確定処理が利用するcurrent要求境界だけはConflictで
停止し、自動再適用・自動mergeを行わない。

現行の`get_effective_trip`、`get_trip_detail_view`、`edit_trip_item`は変更しない。Phase 4の
Working編集commandとD案表示への合成は、この保存境界の上に後続Stepで追加する。

`state_json`のtop-level envelopeは次の3 keyだけとし、すべて必須の配列とする。

- `item_changes`: 既存予定の変更と削除予定を同じ領域へ格納する。
- `temporary_items`: 新規仮追加を格納する。
- `day_instructions`: day-level指示を格納する。

各配列の要素はJSON objectとするが、その内部fieldは各機能を実装する後続Stepで定める。
このenvelopeは格納場所を一貫させるための最小境界であり、Working状態をformal Trip相当の
厳密schemaで検証しない。top-levelに別keyは追加せず、必要な詳細は上記3領域のrecord内で
表現する。

### Step 2: 既存予定のWorking変更

`item_changes`は既存`source_type`（`scheduleItem` / `transport`）とstable
`source_item_id`の組をtargetとし、同じtargetは1 recordへ上書きする。recordは
`disposition`を`changed`または`pending_delete`とし、`changes`へPhase 3直接編集と同じ
意味field名の値を保持する。`pending_delete`は表示対象から除去する指示ではなく、確定時に
削除する予定状態である。通常へ戻す場合はrecordを削除する。

Working変更はtargetの存在と種類、許可field、JSONとしての保存可能性だけを確認する。
未確定・一時的不整合を許容するため、変更値をeffective Tripへ適用してformal Trip schemaを
通すことはしない。保存は`item_changes`だけを更新し、`temporary_items`と
`day_instructions`、初回保存時のeffective revisionを維持する。authoritative TripとDirect
Overrideは変更しない。既存recordはstale後も上書き・解除でき、確定だけを停止する。

### Step 3: 新規予定のWorking仮追加

`temporary_items`はcallerが生成するstable `temporary_id`、既存の`day_id`、共通編集sheetの
手入力値を保持する`values` objectを1 recordとする。同じ`temporary_id`は同じ日で最新値へ
上書きでき、空の`values`から作成して後から再編集できる。`values`は`status`、`start`、
`end`、`time_mode`、`title`、`normal_comment`、`place_name`を受け付ける。AI Instructionは
必須でも保存fieldでもなく、手入力だけで作成・更新できる。

仮追加時はdayの存在とtemporary IDが既存Trip item IDに衝突しないことを確認するが、
Workingの不足状態を許容するためformal Trip schemaは適用しない。既存recordはstale後も
再編集・解除できる。`item_changes`、`day_instructions`、authoritative Trip、Direct Override、初回
保存時のeffective revisionは変更しない。

### Step 4: 仮予定の挿入位置

新しい`temporary_items` recordは`position`に`anchor_source_type`、
`anchor_source_item_id`、`edge`を保持する。anchorは同じ日の既存`scheduleItem`または
`transport`、edgeは`before`または`after`とする。新規作成時はpositionを必須とし、
再編集時に省略した場合は既存positionを維持する。

この境界は選択した既存予定の直前・直後だけを表し、temporary item同士をanchorにする連鎖、
独立した数値order、日付行からの追加やday-level指示は導入しない。positionはWorking表示順を
決める補助情報であり、authoritative TripとDirect Overrideを変更しない。

### Step 5: 日単位のWorking指示

`day_instructions`は既存`day_id`と非空の自然言語`instruction`を1日1 recordで保持する。
同じdayへの再登録は最新内容へ上書きし、解除時はrecordを削除する。新規登録時はdayの存在を
確認するが、既存recordはstale後も再編集・解除できる。

instructionは前後空白を除いてそのまま保存し、CALやFRMで個別予定へ分解・適用しない。
AI requestも生成しない。`item_changes`、`temporary_items`、authoritative Trip、Direct
Override、初回保存時のeffective revisionは変更せず、Step 6のWorking合成表示も行わない。

### Step 6: Working合成表示

`get_working_trip_detail_view`はauthoritative Tripへactive Direct Overrideを適用したeffective
Tripから既存D案表示モデルを生成し、その後にWorking状態を表示用としてだけ重ねる。
`item_changes`は対象entryの表示値へ反映して`working_state: changed`、`pending_delete`は
entryを消さず`working_state: pending_delete`とする。`temporary_items`はpositionのanchor前後へ
`working_state: temporary`として挿入し、`day_instructions`はdayの`working_instruction`へ
保持する。top-level `working`はWorking有無と`stale`を返す。

このread modelはraw Working envelopeをconsumerへ渡さず、formal Trip schemaを適用せず、
authoritative Trip、Direct Override、Working保存内容のいずれも変更しない。正式Tripへの適用、
確定可否判断、AI処理は別Step / Phaseの責務とする。

D案UIからの既存予定編集は`save_working_trip_item_change`へ接続し、通常変更を`changed`、
削除予定化を`pending_delete`として保存し、解除時は`clear_working_trip_item_change`を使う。
Phase 3の`edit_trip_item` / Direct Override境界は維持するが、このWorking編集フローからは呼ばない。
したがってWorking編集だけではeffective revisionやDirect Overrideは変わらず、Workingをstale化しない。

### Step 7: 手動Chat向けcomplete Trip再生成export

`export_working_trip_for_chat`は、手動でChatへ戻して全体整合を取り直すためのCAL semantic
packageを返す。top-levelはformat、task、trip ID、完全なauthoritative Trip、完全なeffective
Trip、Workingのbase/current effective revisionとstale、raw Working envelopeをユーザー意図として
保持する`user_intent`だけとする。画面用のWorking合成モデルは再生成入力にせず、Direct Overrideを
反映したeffective Tripを保存優先の出発点として明示する。

taskは、既存effectiveデータをユーザー意図が要求しない限り維持し、changed、pending_delete、
temporary item、day instructionを旅行全体で整合させ、retained dataのstable IDと内部参照を維持した
formal complete Trip JSON object 1個だけを返すよう求める。Patch、部分Trip、説明、採用指示は出力対象に
しない。staleでもexportは可能とし、Chatがauthoritative/effectiveとrevision差を確認できるようにするが、
CAL側で自動rebase、自動merge、正式Tripへの適用・Validation・採用は行わない。

この境界はJSON objectを返すだけで、provider/API接続、Chatへの自動送信、model/credential、保存先、
正式Trip確定処理、Place enrichmentを持たない。Workingが存在しないTripは、推測した空のユーザー意図を
生成せずNot Foundとする。

### Step 8: Place enrichment

Place enrichmentは、usまたはAIが入力した場所名を置き換える生成処理ではなく、CALが既存の
場所入力を手掛かりに機械的な補完候補を得て、Tripで再利用できる形へ検証する責務とする。
対象は、effective Tripのstable `place_id`を持つPlace、またはWorking temporary itemのstable
`temporary_id`と非空の`place_name`で識別する。Workingへの保存時は場所名だけを引き続き許容し、
enrichmentの未実施、候補なし、取得失敗を保存・表示の失敗にしない。

CALの最小semantic境界は、対象identity、入力済みの名前、利用可能な住所等の検索hintを渡す
provider-neutralな要求と、その対象に対する`address`、`location`、`urls`の補完候補を返す結果である。
CALは型、緯度経度範囲、HTTPS URL、要求した対象identityとの一致を検証する。provider固有request、
credential、課金、rate limit、cache、外部Place IDはこのsemantic契約およびTrip schemaへ入れない。
外部Place IDが永続的に必要だと確認された場合だけ、providerとの寿命や移行を別Issueで決める。

補完結果は候補であり、名前だけで同一Placeと断定したり、同名候補を自動採用したりしない。
一意に扱えない結果は候補のままusまたは後続フローへ返す。採用時も新しい地図用正本は作らず、
existing Placeならformal Placeの同じ`address / location / urls`へ、temporary itemならPhase 5のcomplete
Trip生成時に作るstable Placeへ収束させる。既存の非空値を暗黙に上書きせず、authoritative Tripや
Direct OverrideをこのStepで変更しない。provider/API接続、実行Job、UI、正式採用は未実装とする。

## Phase 5のcomplete candidate受入れ・確定境界

Phase 5の公開semantic commandは
`adopt_working_trip_candidate(trip_id, candidate)`とする。callerはcandidate生成元や
AI Instruction / generation request identityを渡さず、対象Trip IDとformal complete Trip JSON
objectだけを渡す。CALは対象Workingが存在して一意にTripへ属することを確認し、
Working作成時の`base_effective_revision`と確定直前のcurrent effective revisionが一致しない場合は
自動rebase・自動mergeせずConflictとして停止する。stale後もWorkingの表示、編集、再exportは維持する。

既存のwhole-Trip Patch pipelineから、candidate JSON読込、SchemaとTrip ID、semantic / cross-reference、
active Direct Override適用後のeffective Trip、Todoのstable `trip_item_id`参照、same-filesystem staging、
`os.replace`、digest journal recovery、Trip version更新を再利用する。ただし現行の
`_adopt_validated_candidate`とrecovery journalはAI Instruction / generation requestの状態更新に結合して
いるため、そのまま公開しない。共通のatomic adoption層をgenerator-neutralに分離し、既存Patch経路と
Working candidate経路をその上へ接続する。Patch経路の既存state遷移は維持する。

Working candidate経路では、formal candidateのValidationとrevision再確認をreplacement前に完了し、
authoritative TripのreplacementとSQLite Trip version更新を既存recovery方式で一つの採用結果へ収束させる。
採用成功後だけ同じTripのWorking rowを削除する。中断後のrecoveryも、candidateがcurrentになった場合は
version更新とWorking clearまで完了し、old currentのままならWorkingを保持する。active Direct Overrideは
検証に適用するだけで、成功時にも削除・無効化しない。

このcommandはcandidate生成、Chat/API送信、provider/model/credential、candidateの永続queue/history、
FRM表示を持たない。返却値は既存adoption結果に合わせ、少なくとも`trip_id`、`status: adopted`、
`candidate_digest`、更新後`version`、`recovered`を返す。ValidationまたはConflictではauthoritative Tripと
Workingの双方を変更しない。

Phase 5 Step 2では、このcommandの入口としてJSON objectだけをdeep copyして受け取り、登録済みTripに
対応するWorking rowがちょうど1件あることを確認する。Step 3では`status: accepted`を返す直前にWorkingの
captured effective revisionとcurrent effective revisionを比較し、不一致なら自動rebase・自動mergeせず
Conflictで停止する。staleでもWorkingの表示・編集・再exportは継続できる。candidate file pathや生成元情報は受け取らず、
candidateは永続化しない。Step 4では既存のcomplete-candidate gateを再利用し、formal Schema、
semantic / cross-reference、candidate内Trip ID、active Direct Override適用後のeffective Trip、Todoの
stable item参照を確定前にValidationする。失敗時もauthoritative TripとWorkingを変更しない。
atomic adoption、version更新、Working clearはStep 5以降でこの入口へ接続するため、Validation成功後も
authoritative TripとWorkingのどちらも変更しない。
