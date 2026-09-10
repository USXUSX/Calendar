# Chat向け完全Trip JSON生成ガイド

新規Tripの主要経路は **Chatで完成度の高いcomplete Trip JSONを生成 → CALでValidation・内容確認・取込** とする（Issue #108）。既存Tripへの1予定追加のコピペとは別経路である。取込後のCAL編集は微修正に限定しない。

## 現行正本を読む

CAL用JSON作成を依頼されたChatは、毎回GitHub現行mainの次の2文書を読む。会話に残った旧Schemaや記憶だけで生成しない。

- [formal Schema](https://github.com/USXUSX/Calendar/blob/main/Schemas/trip.schema.json)
- [このgeneration guide](https://github.com/USXUSX/Calendar/blob/main/docs/trip-json-generation.md)

Gitが正本で、`Calendar_GD`はmerge後の公式共有コピー。GitHubを読めない場合は、現行mainと一致すると確認された共有コピー、またはusから渡された現行2文書を使う。現行性を確認できなければ生成を確定せず、その不足を伝える。

## 生成手順

1. 旅行名・日付・希望・確定済みの訪問先や予約を読む。必須の日付等が不明ならusに確認する。実旅行の日時・予約を創作しない。
2. 希望に合う少数の場所を調べ、同名施設を住所・地域で照合する。公式情報や保存可能な公開データから、確認できるURL・住所・座標・短いコメントを入れる。調べても不明な値は不明のままにする。候補は訪問確定に変えない。
3. 以下の対応・意味整合を使って完全JSONを1件生成する。提案した日程と予約済みの事実を区別する。
4. UTF-8のcomplete JSON本体を `Calendar_Chat/<trip-id>/candidate.json` へ保存する。ファイル中はJSONオブジェクトだけ。取得元URL・確認日が必要な情報は既存のsummary / details / urls等に短く記し、独自fieldや取得本文を足さない。
5. CAL validatorを実行可能なら実行し、エラーの箇所を修正して同じ完全JSONを更新する。Chat側で実行できなければ「CAL Validation未実行」と伝え、合格を装わない。
6. 日別の行動順・移動・宿泊・候補・未定事項を内容確認し、candidateを渡す。Validation成功だけで正式採用しない。

短い生成指示：

> 現行mainのSchemaとこのガイドを読み、Calendarの正式スキーマに一致する完全な旅行JSONを1個生成してください。ファイル中にはMarkdownや説明文は付けません。確認できた候補・URL・住所・座標・コメントを含め、不明値や予約事実を創作しません。候補は自動選択しません。`Calendar_Chat/<trip-id>/candidate.json`へcomplete JSON本体を保存し、検証結果と残る未定事項を別に短く伝えてください。

## 項目と不明値

キー・型・enumの詳細はSchemaを正本とし、ここでは生成時の使い分けを定める。必須キーは省略しない。任意情報はSchemaが許す`null`または空配列を使う。`searchQuery`は条件がある場合だけ付ける。

| 内容 | 格納先・使い分け |
| --- | --- |
| 旅行全体と日別 | Tripのtitle / dateRange / summary、Dayのdate / title / routeSummary。titleは短いテーマ、routeSummaryは代表エリア・主経路 |
| 行動 | ScheduleItem.action / category。actionはユーザー向けの自然な予定本文。採用済み / 確定済みPlaceは名前を含める（例: `すし善で昼食`）。時刻はtime、移動はTransportだけにする |
| 候補と採用場所 | Placeを1地点1件にしてcandidatePlaceIdsで参照。selectionは明示された採用場所だけ。1候補でも未採用なら空配列。未選択の本文は `小樽で昼食` のような自然文とし、候補名の列挙と分ける |
| 場所未定 | candidatePlaceIdsとselectionを空配列、非空searchQueryに元条件、minSelections / maxSelectionsはnull。架空の「未定」というPlaceは作らない |
| 地点情報 | Place.name / category / address / location / urls / ratingと任意officialUrl。公式と確認済みのURLだけofficialUrlへ設定する。未確認の住所・座標・評価はnull、URLは空配列。locationがある場合は緯度経度の両方が必要 |
| コメント | 通常コメントはScheduleItem.summary、追加事実・出典等はdetails、施設自体の補足はPlace.summary。重複させない |
| 時刻 | fixedは開始必須、rangeは開始・終了必須、undecidedは開始・終了null。所要時間不明はdurationMinutes=null。列車の発着時刻と提案枠を混同しない |
| 移動 | TransportでdayId、両端Place、mode、timeを持ち、Day.transportIdsから参照する。未確認の所要時間を確定値にしない。重要な移動はimportant=true、通常のコネクタ移動はfalse / 省略。ScheduleItemや別タイトルに二重登録しない |
| 予約 | BookingをplaceIdまたはtransportIdへ結ぶ。targetDateは対象日。未予約の予定はpending、実際に予約した証拠がある場合だけbooked。金額不明はnull、予約条件はnotes |
| 準備・Rio | preparation / rioPlanも必須。準備がなければtasks=[]。Rioが対象外と分かる場合だけapplicable=false / careMode=not_applicable。不明ならundecidedとして判断を残す |

CAL上で候補を正式採用すると、selectionと予定本文を一括更新する（#124）。採用済みPlace.nameと一致する本文中の部分を、確認済みofficialUrlへリンクする。通常表示では採用済みの候補一覧を隠す。具体的な更新・表示契約は[旅程詳細モデル](trip-detail-model.md#通常旅程とインライン編集119--121)を正本とする。

予定の確定状態（status）、時刻の表現（time）、予約状態（Booking.status）は別に保つ。確定予定でも時刻未定はあり、開始時刻があるだけで予約済みにはしない。

候補数は新規Trip JSON全体に一律3件制限を置かない。既存予定へのAFM候補追加の件数制限とは別契約である。minSelections / maxSelectionsは分かる場合だけ設定し、最大数は候補件数以内にする。

IDはSchemaに従う英数字・ハイフン・アンダースコアを使い、同じcandidateの再生成では既存対象のIDを維持する。ScheduleItem.dayIdは親Dayと一致させ、日内orderはScheduleItemとTransportを合わせて重複させない。selectionはcandidatePlaceIdsの部分集合にする。移動のdayIdとDay.transportIds、予約の対象参照と日付を対応させ、参照漏れや不要なPlaceを残さない。

日跨ぎ時刻、未確定の移動端点など、現在のSchemaでそのまま表現できない入力は、事実を偽装して通さず不足を伝える。予約済みの複数泊は開始日をtargetDateとし、チェックアウト日等の条件をnotesへ記す。移動への任意コメントfieldはないため、予約条件はBooking.notes、それ以外の必要な補足はTrip.summary等に対象を明記する。専用fieldが必要な実用途が判明した場合はSchemaと利用側を同じ変更範囲で検討する。

## 受渡しとCAL採用の境界

| 場所 | 役割 |
| --- | --- |
| Calendar Git / Calendar_GD | Schema・guideの正本 / 公式参照コピー |
| `/Users/us/Tools/GoogleDrive/Calendar_Chat/<trip-id>/candidate.json` | 新規Tripの未採用complete JSON本体（Envelopeなし）。再生成で同じファイルを更新してよく、履歴管理を追加しない |
| Calendar_Local | CALで採用後の正式TripとSQLite等の通常状態。Chatから直接書き換えない |
| `/Users/us/Tools/GoogleDrive/Calendar_Chat/<trip-id>/` | 新規・既存Trip共通の授受先。既存TripのcontextはCAL所有、candidateはChat所有のEnvelope。Calendar_GDとは分ける |

受渡しフォルダへアクセスできないChatは、`candidate.json`を添付し、対象の`<trip-id>/`への配置をusに依頼する。保存できたと主張したり、Calendar_GDやCalendar_Localを代わりに使ったりしない。新規Tripは明示的な取込操作で採用する。

Git正本で次を実行する。このCLIはSchemaとsemantic validationを両方行い、保存状態を変更しない。

```sh
python3 scripts/validate_trip.py '/Users/us/Tools/GoogleDrive/Calendar_Chat/<trip-id>/candidate.json'
```

エラーがあれば該当パスとエラーだけをChatへ返し、部分パッチではなく同じcomplete JSONを直す。CALの取込操作がValidation・内容確認・正式採用を担当する。Chatが検証済みファイルをCalendar_Localへコピーする運用にはしない。

Issue #110で[新規JSON取込](trip-json-import.md)へ接続した。Frameで共有candidateを選び、Validation結果と内容を確認して新規登録する。既存Tripは同じIDで置換しない。日本語ラベルの全Trip補正UIは置き換え、1予定追加コピペは維持する。

## 北海道4日間の代表例と内容確認

[代表JSON](../Samples/hokkaido-4days-candidate.json)は、2027-06-12〜15を仮の日程とした公開施設ベースの合成例。実旅行・実予約・usの採用済み希望ではない。出典と確認内容は[Samples README](../Samples/README.md)を参照する。

札幌を拠点に、到着日、小樽日帰り、札幌市内、帰路の順とし、遠距離の詰込みを避ける。3泊、往復の主要鉄道移動、候補未選択、店未定、住所・URL・座標・コメント・pending予約を含む。時刻は未定とし、将来ダイヤや空室を保証しない。候補訪問時の市内移動は訪問先選択後に決める。

Schemaで今回必要な情報を表現できるため変更は不要。Validationとは別に、日程と対象日、宿泊回数、往復経路、候補の非採用、未定値、参照の整合、行動・移動・コメントの重複がないことを確認する。料金、営業日、予約、交通ダイヤは実旅行決定時に再確認する。

## 新規Trip主要経路の最終確認（#126）

[代表入力と出典](../Samples/README.md#新規trip主要経路の最終確認126)から生成した[complete JSON](../Samples/hokkaido-import-review.json)を使う。確定Placeを含む本文、未選択の複数候補、3泊、重要 / コネクタ移動、fixed / range / undecided、booked / pendingを含む。日時とbookedは明示した合成入力であり、実旅行・実予約を意味しない。

このcandidateを一時受渡し先に置き、Frame `/calendar/import` で読込・Validation・内容確認・新規登録し、通常旅程で候補正式採用と本文・時刻・コメントの直接編集を確認する。テストではDB・Trip root・Chat root・candidate rootをすべて一時環境へ明示する。Calendar_Localや運用共有先には保存しない。

## 既存Tripの変更

新規Trip取込は既存Tripの上書き経路ではない。既存Tripの主要なChat往復は次節の共有Envelopeを使う。既存Working exportとAI InstructionのJSON Patch経路も保持する。いずれもCALがValidationと正式採用を担当し、Chatは正式ファイルを直接置換しない。

## 継続するChat往復（#112）

既存Tripの調査・候補比較・大きな編集はChatを主に使い、CALは旅程正本、Validation、
Place同定・URL/住所/座標補完、天気、直接編集、時刻矛盾の確認を引き続き担当する。

授受先は `/Users/us/Tools/GoogleDrive/Calendar_Chat/<trip-id>/`（#114）。
GoogleDrive配下の既存同期を使い、cloud ChatはDrive上のCalendar_Chat、local Chatは同じローカル同期フォルダへアクセスする。
Calendar_LocalはDrive同期対象ではないため、旧 `Calendar_Local/chat` は以後の授受に使わない。
経路によってEnvelopeを変えず、履歴ファイルは増やさない。Calendar_GDは公式同期の削除対象を含む参照コピーなので、運用授受を混在させない。
同じ `<trip-id>/candidate.json` でも、新規Tripは初回登録専用のcomplete JSON本体、既存Tripは以下のEnvelopeを使う。新規取込ではEnvelopeを採用せず、既存Tripの継続往復ではcomplete JSON本体だけを採用しない。

- `context.json` はCAL所有。`trip_id / current_revision / effective_revision / trip / instructions`。
  `trip` は現在のeffective complete Tripで、`instructions` は未処理指示の `id / instruction`。
  `current_revision` は正式Tripの `trip_version / trip_hash`、`effective_revision` は
  同じversionとDirect Overrideを含む `effective_hash`。Chatは書き換えない。
- `candidate.json` はChat所有。次の最小Envelopeだけを同じファイルへ保存する。
  `trip` は現行formal Schemaのcomplete Trip。独自の旅程Schema、部分Patchではない。

```json
{
  "trip_id": "contextのtrip_id",
  "base_revision": {"trip_version": 1, "effective_hash": "contextのeffective_revisionをそのまま複製"},
  "handled_instruction_ids": [],
  "trip": {}
}
```

これはEnvelope形状の説明であり、`trip: {}` は有効な旅程ではない。
Chatは作業開始時に最新contextを読み、`trip`を出発点に既存ID・予約事実・未変更部分を保持して編集する。
対応した指示だけを`handled_instruction_ids`へ入れ、新しい指示や未対応指示は残す。
候補を自動選択せず、不明情報を創作しない。共有先へアクセスできなければcandidateを添付し配置を依頼する。
Chatが書いてよいのはこのcandidateだけで、正式 `trips/`・SQLite・contextを直接更新しない。

CALの通常編集、Place補完、指示追加、正式採用後にcontextを自動更新し、Trip表示・再読込時にも更新する。
手動「Chatへ出力」は不要。Frameの通常旅程画面からChatへの指示を追加でき、API/AFM workerは起動しない。
通常画面load / reloadは`load_trip_detail_view(trip_id)`を呼ぶ。CALがcandidateを読んでrevision / Schema /
semantic / 未処理指示 / Todo参照を検証し、valid/currentなら確認画面を挟まず正式採用して最新viewを返す。
未反映差分preview・保留・反映ボタンは通常UIに置かない。invalid/stale時も現在の正式旅程を返し、
`view.chat.message`だけをエラー表示する。`view.instructions`はpendingの一覧。
直接編集後の再表示は`get_trip_detail_view`でcontextを共有し、編集応答の途中でcandidateを採用しない。

staleは最新contextからChatで再作成する。不正JSON・Schema・semantic不整合は修正して再確認する。
staleの自動merge・不正値の自動修復はしない。採用時もrevision、確認snapshot、未処理指示、Todo参照を再検証する。
Validation済みcomplete TripにはDirect Overrideの内容が含まれるため、正式採用と同じtransactionでOverrideを解除する。
候補内で編集された値に古いOverrideを重ねない。既存Workingは保持され、正式version更新でstaleとなる。
採用成功後だけ対応済み指示を処理済みにし、同じcandidateを削除し、新contextを生成する。
CALは既存のatomic adoption・中断journalを使い、正式TripとSQLiteの更新責務を所有する。
context書込み失敗では保存済みCAL状態を巻き戻さず、共有先を確認して再読込する旨を返す。

通常画面以外の既存確認用commandとして `get_chat_context(trip_id)`、`add_chat_instruction(instruction_id, trip_id, instruction)`、
`review_chat_candidate(trip_id)`、`adopt_chat_candidate(trip_id, candidate, confirmed=True)`。
reviewは `status=absent / stale / invalid / ready`、`ready`、未処理`instructions`を返し、
合格時だけ確認用`candidate / view / changes / handled_instructions`を返す。
`CalendarDomain(db_path, trip_root, chat_root=...)`でテスト・隔離実行用の共有先を明示できる。
未指定時は上記Calendar_Chatを使い、正式Tripのrootとは独立する。テストでは必ず一時共有先を指定する。
採用は確認snapshotと共有candidateが一致しない場合も拒否する。任意の共有rootはHTTPから指定できない。

合成北海道4日間を使う `sh Tests/chat-exchange.test.sh` で、CAL編集→context→Chat相当candidate→
通常loadでの自動採用、stale/invalid/途中変更の拒否、指示・Override処理、中断後の収束を確認する。
FrameのHTTPとiPad mini相当幅の代表操作でも同じ契約を確認する。
#114のproduction切替では正式Trip/SQLiteを変更せずcontextを再生成し、Drive側の同じ内容の読取りまで確認する。
物理端末での実用性・Phase 8の判断は#96で扱う。

### #116の編集情報

contextのTripには任意のDay.areas（順序付きname/location）、ScheduleItem.candidateJudgments、
Transport.serviceNameとmode=shinkansenを保持できる。予約不要でも旅程上重要な移動は任意booleanのimportantで保持する（省略時false）。予約済み・予約予定は既存Bookingを使う。詳細は[表示・更新契約](trip-detail-model.md#通常旅程とインライン編集119--121)。rangeは開始＋durationMinutesから終了を計算する。
予定単位instructionsはsource_item_idを持つ。Chatは対象を解決して結果をcandidateへ反映し、
対応済みのIDをhandled_instruction_idsへ列挙する。指示文自体を予定本文に転記しない。

Place.officialUrlは確認済み公式リンク、urlsは参考リンク。本文actionは「すし善で夕食」のような自然文を保持し、施設名をPlace.nameと一致させる。レストランの食べログ点数は既存rating（source=食べログ、observedAt付き）へ確認済みの値だけ記す。
