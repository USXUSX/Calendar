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

状態は次の順で導出する。

1. 時刻が`undecided`、または選択数が`minSelections / maxSelections`を満たさなければ`undecided`。
2. それ以外で時間が`range`なら`tentative`。
3. それ以外は`confirmed`で、状態装飾を付けない。
4. 候補が複数あれば`has_candidates`を独立して返す。これは確定・暫定・未定の判定を上書きしない。

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

## Phase 3への受渡し

Phase 3は、表示モデルの`direct_edit_paths`を使って具体値編集をDirect Overrideへ接続し、
保存前確認、複数fieldの一括Validation、結果表示を実装する。候補判断と局所AI executorは
Phase 3の直接編集を置き換えず、後続Phaseでこの同じ意味境界へ接続する。
