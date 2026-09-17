# 地図の座標補完・位置保存

Goal 2 Phase 2（Calendar #167 / Frame #114）。追加修正は [#167 の追加指示](https://github.com/USXUSX/Calendar/issues/167#issuecomment-5713374212) に従う。Phase 1の地点集約・番号・候補の意味は維持する。

## 取り込み

Frameの新規complete JSON登録と、既存TripのChat candidate自動採用で補完する。CALの`prepare_import_locations`が現行地図対象から検索planを生成し、Frameは既存ブラウザ用Maps SDKのPlaces API (New) Text Searchを使う。名称＋住所、住所なしなら名称＋その日の旅行エリア、両方なしなら名称を、一度だけ検索する。これは検索文字列の選択順であり、結果なしで条件を変えて再検索するものではない。

検索対象は実際のPlace座標がない地図表示対象とDay.areas。エリアは自身の名称を使う。既存座標は検索・上書きしない。既存Tripは同じ安定Place IDのeffective座標（Direct Overrideを含む）を入力JSONより優先する。名称＋住所が完全一致する別IDは同一点として一度検索し、同じ座標と施設IDを未登録IDへ保存する。Day.areasは同じDay ID・名称の保存済み位置を保持する。あいまいな名称一致やTrip間のグローバルPlace統合はしない。

Frameは先頭結果の緯度経度とGoogle Place IDを地点ID別`coordinate_results`で返す。結果は`{location:{latitude,longitude},googlePlaceId}`。正式PlaceおよびDay.areasの任意`googlePlaceId`に保存し、既存locationだけのJSONも受け付ける。Google Place IDとCALの安定Place ID、表示先のmapPlaceIdは別の値。取得済み座標へのID後付けを目的とした再検索はしない。CALは対象と不足状態を再計算し、有効な座標だけをcomplete Tripへ反映して従来の採用を行う。対象外の結果は利用しない。検索失敗・結果なし・不正な検索座標は未取得として取り込みを続ける。取り込み応答の`coordinates`は`filled / missing / existing`件数（地図対象の同一地点を重複しない単位と日別エリア）で、Frameは登録後の旅程画面へ簡潔に表示する。

ブラウザの通常load/reloadはreadyなChat candidateを受け取り、座標補完後に既存adopt操作へ渡す。検索中のcandidate変更・revision競合は従来のCAL検証で拒否し、正式旅程を保持する。候補比較・追加の確認画面は置かない。ブラウザ以外の呼出側は同じplan/result契約を使える。検索結果を渡さない呼出では不足座標を未取得として採用する。

## 地図編集

`get_map_location(trip_id, place_id)`は対象地点の現在座標と同じ検索文字列を返す。編集モードだけに「位置を設定」「位置を修正」を表示する。未登録地点は先頭検索結果を仮Pinへ表示し、検索不能でも地図指定できる。登録済み地点は現在Pinから始め、再検索しない。Pinドラッグと地図タップは保存前の仮位置だけを変え、取消はCALを変更しない。

`save_map_location(command_id, trip_id, place_id, location, expected_location, google_place_id=None)`が有限の緯度経度・地図対象・読取時点の座標を確認し、CAL Direct Overrideへ保存する。完全一致で同一地点としたPlace IDは一緒に更新する。日別エリアは`area:<day_id>:<index>`で同じ編集に接続する。検索結果または保存済みPinを動かさず保存すると施設IDを保持し、ドラッグ・地図タップの手動位置は施設IDをnullにする。正式基礎JSONを手編集せず、effective Trip・Chat context・再表示へ反映する。地図対象指定`mapPlaceId`は変更しない。候補がPhase 1で表示対象の代表地点座標を仮表示していても、その候補自体の位置設定と区別する。

## エリア・予定・候補の追加

既存地点を選べばそのCAL Place ID・Google Place ID・保存済み座標を再利用し、再検索しない。新しい場所名なら保存時に同じ先頭結果取得を行う。`prepare_location_inputs`が名称・住所・当日エリアからplanを返し、Frameが結果を既存の編集commandへ渡す。エリア・予定・候補・1予定貼付も同じ検索処理を使い、失敗はlocation=nullのまま保存する。候補の追加は既存選択を変えない。エリア選択では地点の名称・座標・施設IDを保存する。通常UIは「位置取得済み」「位置未登録・地図で補正」のみを表示し、補正は既存の地図編集へ接続する。施設候補一覧・確認ダイアログ・別providerへの代替取得は設けない。

Google接続設定と画面検証はFrame README、実行・確認結果は#167 / Frame #114を参照する。経路・複数候補比較・信頼度・一括座標上書きは対象外。

## Mac実機レビュー後の調整

[#167のMacレビュー](https://github.com/USXUSX/Calendar/issues/167#issuecomment-5721841774)により、Placeの任意`mapDisplayName`を追加する。`edit_trip_item`の`map_display_names`（対象Place IDから文字列への辞書）で、その予定の確定地点・候補の表示名だけをDirect Overrideへ保存できる。空欄はnullとし正式名称へ戻る。正式名称・URL・施設ID・座標を変更せず、位置の再検索も行わない。Chat contextとeffective Tripにも保持する。表示名を使用する範囲は地図ラベルと地図下の一覧に限り、旅程・詳細・検索文字列は正式名称を使う。

位置補正を旅程編集から開始した場合は、保存・取消とも元の予定または日別情報の編集状態・スクロールへ戻る。未保存編集がある場合は先に保存を促す。地図から直接開始した場合は地図に残る。
