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
再編集・解除できる。挿入位置や既存予定との上下関係はStep 4の責務であり、このStepでは
保存しない。`item_changes`、`day_instructions`、authoritative Trip、Direct Override、初回
保存時のeffective revisionは変更しない。
