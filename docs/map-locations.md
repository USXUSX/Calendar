# 地図の座標補完・位置保存

Goal 2 Phase 2（Calendar #167 / Frame #114）。Phase 1の地図表示対象・集約・番号・候補・通常表示は維持する。

## 取り込み

Frameの新規complete JSON登録と、既存TripのChat candidate自動採用で補完する。CALの`prepare_import_locations`が現行地図対象から検索planを生成し、Frameは既存ブラウザ用Maps SDKのPlaces API (New) Text Searchを使う。名称＋住所、住所なしなら名称＋その日の旅行エリア、両方なしなら名称を、一度だけ検索する。これは検索文字列の選択順であり、結果なしで条件を変えて再検索するものではない。

検索対象は実際のPlace座標がない地図表示対象。既存座標は検索・上書きしない。既存Tripは同じ安定Place IDのeffective座標（Direct Overrideを含む）を入力JSONより優先する。名称＋住所が完全一致する別IDは同一点として一度検索し、同じ座標を未登録IDへ保存する。あいまいな名称一致やTrip間のグローバルPlace統合はしない。

Frameは先頭結果の緯度経度だけを地点ID別`coordinate_results`で返す。CALは対象と不足状態を再計算し、有効な座標だけをcomplete Tripへ反映して従来の採用を行う。対象外の結果は利用しない。検索失敗・結果なし・不正な検索座標は未取得として取り込みを続ける。取り込み応答の`coordinates`は`filled / missing / existing`件数（地図上の同一地点を重複しない単位）で、Frameは登録後の旅程画面へ簡潔に表示する。

ブラウザの通常load/reloadはreadyなChat candidateを受け取り、座標補完後に既存adopt操作へ渡す。検索中のcandidate変更・revision競合は従来のCAL検証で拒否し、正式旅程を保持する。候補比較・追加の確認画面は置かない。ブラウザ以外の呼出側は同じplan/result契約を使える。検索結果を渡さない呼出では不足座標を未取得として採用する。

## 地図編集

`get_map_location(trip_id, place_id)`は対象地点の現在座標と同じ検索文字列を返す。編集モードだけに「位置を設定」「位置を修正」を表示する。未登録地点は先頭検索結果を仮Pinへ表示し、検索不能でも地図指定できる。登録済み地点は現在Pinから始め、再検索しない。Pinドラッグと地図タップは保存前の仮位置だけを変え、取消はCALを変更しない。

`save_map_location(command_id, trip_id, place_id, location, expected_location)`が有限の緯度経度・地図対象・読取時点の座標を確認し、CAL Direct Overrideへ保存する。完全一致で同一地点としたPlace IDは一緒に更新する。正式基礎JSONを手編集せず、effective Trip・Chat context・再表示へ反映する。地図対象指定`mapPlaceId`は変更しない。候補がPhase 1で表示対象の代表地点座標を仮表示していても、その候補自体の位置設定と区別する。

## 予定追加

既存地点を選べばそのPlace IDと既存座標を利用する。新しい場所名なら座標nullで新Placeと予定を保存する。保存時に外部検索しない。位置は後で地図編集から設定する。

Google接続設定と画面検証はFrame README、実行・確認結果は#167 / Frame #114を参照する。経路・複数候補比較・信頼度・一括座標上書きは対象外。
