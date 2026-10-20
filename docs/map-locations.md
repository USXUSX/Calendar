# 地図の座標補完・位置保存

Goal 2 Phase 2（Calendar #167 / Frame #114）。追加修正は [#167 の追加指示](https://github.com/USXUSX/Calendar/issues/167#issuecomment-5713374212) に従う。Phase 1の地点集約・番号・候補の意味は維持する。

## 取り込み

Frameの手動新規complete JSON登録と、RDC専用コマンドの旅程登録・変更で補完する。CALの`prepare_import_locations`が現行地図対象から検索planを生成し、Frameは既存ブラウザ用Maps SDKのPlaces API (New) Text Searchを使う。名称＋住所、住所なしなら名称＋その日の旅行エリア、両方なしなら名称を、一度だけ検索する。ただし名称が「自宅」の地点は旅行エリアを使わず、住所があれば住所だけで検索する。住所なしは`skip_search=true`として検索せず、未登録のまま保持する（返却された検索結果も採用しない）。保存済み座標と地図での手動設定は従来どおり使える。この規則は地点入力と地図編集にも適用する。これは検索文字列の選択順であり、結果なしで条件を変えて再検索するものではない。

検索対象は実際のPlace座標がない地図表示対象とDay.areas。エリアは自身の名称を使う。既存座標は検索・上書きしない。既存Tripは同じ安定Place IDのeffective座標（Direct Overrideを含む）を入力JSONより優先する。名称＋住所が完全一致する別IDは同一点として一度検索し、同じ座標と施設IDを未登録IDへ保存する。Day.areasは同じDay ID・名称の保存済み位置を保持する。あいまいな名称一致やTrip間のグローバルPlace統合はしない。

Frameは先頭結果の緯度経度とGoogle Place IDを地点ID別`coordinate_results`で返す。結果は`{location:{latitude,longitude},googlePlaceId}`。正式PlaceおよびDay.areasの任意`googlePlaceId`に保存し、既存locationだけのJSONも受け付ける。Google Place IDとCALの安定Place ID、表示先のmapPlaceIdは別の値。取得済み座標へのID後付けを目的とした再検索はしない。CALは対象と不足状態を再計算し、有効な座標だけをcomplete Tripへ反映して従来の採用を行う。対象外の結果は利用しない。検索失敗・結果なし・不正な検索座標は未取得として取り込みを続ける。取り込み応答の`coordinates`は`filled / missing / existing`件数（地図対象の同一地点を重複しない単位と日別エリア）で、Frameは登録後の旅程画面へ簡潔に表示する。

通常load/reloadによるcandidate自動採用は#205で停止した。専用CLIはtrip-planで同じplanを返し、通常Chatではtrip-resolveが既存FrameのGoogle Maps接続を使って不足地点を検索し、applyへcoordinate_resultsを渡す。Frame画面の表示・再読込は不要。検索対象の結果キーが欠ける要求は未検索として拒否し、検索済みで結果なしの地点だけnullとして未取得を許容する。CALは既存座標・自宅設定を維持して補完し、filled/missing/existingをreceiptへ返す。取得不能を成功扱いせず、必要ならFrameの地図編集で補正する。

## 地図編集

`get_map_location(trip_id, place_id)`は対象地点の現在座標と同じ検索文字列を返す。編集モードだけに「位置を設定」「位置を修正」を表示する。未登録地点は先頭検索結果を仮Pinへ表示し、検索不能でも地図指定できる。登録済み地点は現在Pinから始め、再検索しない。Pinドラッグと地図タップは保存前の仮位置だけを変え、取消はCALを変更しない。

`save_map_location(command_id, trip_id, place_id, location, expected_location, google_place_id=None)`が有限の緯度経度・地図対象・読取時点の座標を確認し、CAL Direct Overrideへ保存する。完全一致で同一地点としたPlace IDは一緒に更新する。日別エリアは`area:<day_id>:<index>`で同じ編集に接続する。検索結果または保存済みPinを動かさず保存すると施設IDを保持し、ドラッグ・地図タップの手動位置は施設IDをnullにする。正式基礎JSONを手編集せず、effective Trip・Chat context・再表示へ反映する。地図対象指定`mapPlaceId`は変更しない。候補がPhase 1で表示対象の代表地点座標を仮表示していても、その候補自体の位置設定と区別する。

## エリア・予定・候補の追加

既存地点を選べばそのCAL Place ID・Google Place ID・保存済み座標を再利用し、再検索しない。新しい場所名なら保存時に同じ先頭結果取得を行う。`prepare_location_inputs`が名称・住所・当日エリアからplanを返し、Frameが結果を既存の編集commandへ渡す。エリア・予定・候補・1予定貼付も同じ検索処理を使い、失敗はlocation=nullのまま保存する。候補の追加は既存選択を変えない。エリア選択では地点の名称・座標・施設IDを保存する。通常UIは「位置取得済み」「位置未登録・地図で補正」のみを表示し、補正は既存の地図編集へ接続する。施設候補一覧・確認ダイアログ・別providerへの代替取得は設けない。

Google接続設定と画面検証はFrame README、実行・確認結果は#167 / Frame #114を参照する。経路・複数候補比較・信頼度・一括座標上書きは対象外。

## Mac実機レビュー後の調整

[#167のMacレビュー](https://github.com/USXUSX/Calendar/issues/167#issuecomment-5721841774)により、Placeの任意`mapDisplayName`を追加する。`edit_trip_item`の`map_display_names`（対象Place IDから文字列への辞書）で、その予定の確定地点・候補の表示名だけをDirect Overrideへ保存できる。空欄はnullとし正式名称へ戻る。正式名称・URL・施設ID・座標を変更せず、位置の再検索も行わない。Chat contextとeffective Tripにも保持する。表示名を使用する範囲は地図ラベルと地図下の一覧に限り、旅程・詳細・検索文字列は正式名称を使う。

位置補正を旅程編集から開始した場合は、保存・取消とも元の予定または日別情報の編集状態・スクロールへ戻る。未保存編集がある場合は先に保存を促す。地図から直接開始した場合は地図に残る。

## 選択経路・公式画像の表示契約（#174）

移動編集の「地図に経路を表示」は`edit_trip_item`の`show_on_map`でTransport.showOnMapを保存する。重要な移動とは独立し、表示モデルの`show_on_map`で再編集時の状態を返す。
Transportの任意showOnMap=trueだけをday.map_routesへ投影する。route_id、mode、origin/destination（place_id、name、location、googlePlaceId）を渡す。省略時は非表示。日別・全日表示はFRMが絞り込み、車の経路はFRMのGoogle Routesで取得・描画する。鉄道は下記N02由来のCAL派生形状とGoogle Maps経路検索リンクを表示する（#244）。車の経路形状はCALに保存しない。
map_stops.pointsにはcategoryとofficial_urlも渡す。FRMはattractionかつ公式URLありの地点に限り、フォーカス時の公式og:imageを1枚表示できる。画像URLや画像本体はCALへ書き戻さない。

画像取得元はCALのget_place_image_source(trip_id, place_id)から取得する。これはeffective TripのattractionかつofficialUrlのみを返す読み取りで、Chat candidateの採用を起動しない。

## 固定の自宅

CAL LocalDataの`settings/home.json`に`address`、`location:{latitude,longitude}`、任意`googlePlaceId`を登録できる。個人の値はGit・共有参照コピーへ入れない。設定ありの場合は名称（前後空白を除く）が「自宅」のPlaceに設定を優先し、Trip内の住所・座標・施設IDやDirect Overrideより優先する。地点IDや名称、その他の項目は変更しない。

新規取込・Chat採用・既存effective Trip・context・地点入力で共通利用する。既存の正式JSONは読込だけでは書き換えない。自宅の地図編集による個別位置保存は受け付けず、住所変更は共通設定で行う。設定更新は次回読込から反映され、Chatのeffective revisionにも含まれる。設定がない環境は従来動作で、壊れた設定はエラーとして通知する。

初日・最終日の鉄道本体の出発／到着駅は地図対象に残す。新幹線等の前後にある自宅アクセス区間は対象外とし、自宅そのものは鉄道境界のtransport端点でも表示しない。既存のflight境界除外と車旅行の範囲・地点順序・map_routesは維持する（#218）。

旅程画面の直接操作は[正式要求・版照合・receipt契約](direct-schedule.md#画面の正式要求calendar-238)を使用する。指示保存とAI処理、正式保存とview/Google/DSP反映を区別する。

## 国内鉄道路線の形状（#244）

Transportの任意 `railRoute` に利用区間を順番に指定する。省略/nullの旧Tripも有効で、線は生成せずリンクを維持する。

```json
{"railRoute":{"legs":[{"operator":"西日本旅客鉄道","line":"山陽新幹線","from":"福山","to":"新大阪","via":[]},{"operator":"東海旅客鉄道","line":"東海道新幹線","from":"新大阪","to":"新横浜","via":[]}]}}
```

`operator` / `line` / 駅名はN02の運営会社・路線名・駅名と完全一致させる。from/toは各区間の駅、viaはその区間内の必要な経由駅の順序付き配列。隣接区間は同じ駅で接続する。先頭/末尾駅はTransport端点Placeのname（末尾の「駅」は除ける）と一致させる。新幹線と在来線の区分も照合する。異なる駅コードの同名駅、路線不明、不接続、viaでも一意に決まらない環状経路は未生成とし、最短経路・他路線・直線へ置き換えない。同じ駅コードの複数platform形状は同一駅として扱う。N02駅形状上の頂点を区間端点にし、Place座標から駅への補間線を加えない。

正式JSONには指定だけを保持する。`get_trip_edit_view` / `get_trip_detail_view` のday.map_routesの鉄道に `rail` を付ける。ready時は `geometry:{type:"MultiLineString",coordinates:[[[longitude,latitude],...],...]}`、source_version、source_sha256、source_url、license_url、attribution、cache_keyを返す。複数路線は別の線として描き、乗換駅の異なるplatform間を直線でつながない。これは鉄道路線の表示であり運行状況・列車の走行実績ではない。

unavailable時は形状なしでreasonを返す：route_unspecified / endpoint_mismatch / line_not_found / station_not_found / ambiguous_station / mode_mismatch / leg_connection_mismatch / repeated_station / disconnected / ambiguous_path / data_unavailable。FRMは状態を表示して既存リンクを残す。

描画read時にローカルデータから抽出し、`Calendar_Local/rail/derived/<fingerprint>.json` へ再生成可能な派生データを保存する。元ZIPのSHA-256・抽出方式版・mode・railRoute・両端点全値をキーにし、変更前の形状を再利用しない。元データがない場合も古いcacheを表示しない。通常表示からネットワーク取得や正式Trip更新は行わず、SQLiteの更新lock外で生成する。

既存の編集commandは `changes.rail_route`（nullで解除）を受け付ける。他fieldだけの部分更新では保持する。画面は既存 `apply_trip_operation`、Chatの部分変更は専用CLI `trip-operation` を使い、request_id・expected_revision・committed receipt・lookupは既存正式要求と同じ。新規生成・complete Trip更新も同じrailRouteを保持する。
