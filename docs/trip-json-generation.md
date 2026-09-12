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
3. 以下の対応・意味整合と[生成品質の確認](#生成品質の確認)を使って完全JSONを1件生成する。提案した日程と予約済みの事実を区別する。
4. UTF-8のcomplete JSON本体はチャット本文へ全文展開せず、cloud Chatは接続中のGoogle Drive上の `Calendar_Chat/<trip-id>/candidate.json` へ保存する。local Chatは同じ同期フォルダ `/Users/us/Tools/GoogleDrive/Calendar_Chat/<trip-id>/candidate.json` を使う。ファイル中はJSONオブジェクトだけ。取得元URL・確認日が必要な情報は既存のsummary / details / urls等に短く記し、独自fieldや取得本文を足さない。
5. Chatは生成したJSONの構造と内容を自己確認するが、CAL正式Validationを実行済みとは扱わない。Schema・semanticの正式ValidationはCALが新規Trip取込時に行い、エラー時はその結果に従って同じ`candidate.json`を修正する。
6. 日別の行動順・移動・宿泊・候補・未定事項を内容確認し、candidateを渡す。チャット側の最終表示は保存した `Calendar_Chat/<trip-id>/candidate.json` と残る未定事項だけを簡潔に返す。CAL Validation成功前に正式採用済みとは扱わない。

短い生成指示：

> 現行mainのSchemaとこのガイドを読み、Calendarの正式スキーマに一致する完全な旅行JSONを1個生成してください。ファイル中にはMarkdownや説明文は付けません。確認できた候補・URL・住所・座標・コメントを含め、不明値や予約事実を創作しません。候補は自動選択しません。保存・最終表示は上記の生成手順に従ってください。

## 項目と不明値

キー・型・enumの詳細はSchemaを正本とし、ここでは生成時の使い分けを定める。必須キーは省略しない。任意情報はSchemaが許す`null`または空配列を使う。`searchQuery`は条件がある場合だけ付ける。

| 内容 | 格納先・使い分け |
| --- | --- |
| 旅行全体と日別 | Tripのtitle / dateRange / summary、Dayのdate / title / routeSummary。titleは短いテーマ、routeSummaryは代表エリア・主経路 |
| 行動 | ScheduleItem.action / category。actionはユーザー向けの自然な予定本文。採用済み / 確定済みPlaceは名前を含める（例: `すし善で昼食`）。時刻はtime、移動はTransportだけにする |
| 候補と採用場所 | Placeを1地点1件にしてcandidatePlaceIdsで参照。selectionは明示された採用場所だけ。1候補でも未採用なら空配列。未選択の本文は `小樽で昼食` のような自然文とし、候補名の列挙と分ける |
| 場所未定 | candidatePlaceIdsとselectionを空配列、非空searchQueryに元条件、minSelections / maxSelectionsはnull。架空の「未定」というPlaceは作らない |
| 地点情報 | Place.name / category / address / location / urls / ratingと任意officialUrl。公式と確認済みのURLだけofficialUrlへ設定する。未確認の住所・座標・評価はnull、URLは空配列。locationがある場合は緯度経度の両方が必要 |
| コメント | 通常コメントはScheduleItem.summary、追加事実・出典等はdetails、施設自体の補足はPlace.summary。予約の重要コメントはBooking.notes、予約に属さない予定固有の重要コメントはScheduleItem / Transportの任意importantComment。情報の所有箇所に置き、他へ複製しない |
| 時刻 | fixedは開始必須、rangeは開始・終了必須、undecidedは時刻未定、noneは時刻設定が不要。どちらもstart / end / durationMinutesはnullとし、順序はorderで表す。所要時間不明はdurationMinutes=null。列車の発着時刻と提案枠を混同しない |
| 移動 | TransportでdayId、両端Place、mode、timeを持ち、Day.transportIdsから参照する。未確認の所要時間を確定値にしない。重要な移動はimportant=true、通常のコネクタ移動はfalse / 省略。ScheduleItemや別タイトルに二重登録しない |
| 予約 | BookingをplaceIdまたはtransportIdへ結ぶ。targetDateは対象日。未予約の予定はpending、実際に予約した証拠がある場合だけbooked。金額不明はnull、予約条件はnotes |
| 準備・Rio | preparation / rioPlanも必須。準備がなければtasks=[]。Rioが対象外と分かる場合だけapplicable=false / careMode=not_applicable。不明ならundecidedとして判断を残す |

CAL上で候補を正式採用すると、selectionと予定本文を一括更新する（#124）。採用済みPlace.nameと一致する本文中の部分を、確認済みofficialUrlへリンクする。通常表示では採用済みの候補一覧を隠す。具体的な更新・表示契約は[旅程詳細モデル](trip-detail-model.md#通常旅程とインライン編集119--121)を正本とする。

予定の確定状態（status）、時刻の表現（time）、予約状態（Booking.status）は別に保つ。具体的な判断と生成後の確認は次節に従う。

候補数は新規Trip JSON全体に一律3件制限を置かない。既存予定へのAFM候補追加の件数制限とは別契約である。minSelections / maxSelectionsは分かる場合だけ設定し、最大数は候補件数以内にする。

IDはSchemaに従う英数字・ハイフン・アンダースコアを使い、同じcandidateの再生成では既存対象のIDを維持する。ScheduleItem.dayIdは親Dayと一致させ、日内orderはScheduleItemとTransportを合わせて重複させない。selectionはcandidatePlaceIdsの部分集合にする。移動のdayIdとDay.transportIds、予約の対象参照と日付を対応させ、参照漏れや不要なPlaceを残さない。

日跨ぎ時刻、未確定の移動端点など、現在のSchemaでそのまま表現できない入力は、事実を偽装して通さず不足を伝える。予約済みの複数泊は開始日をtargetDateとし、チェックアウト日等の条件をnotesへ記す。移動の予約条件はBooking.notes、予約に属さない重要コメントはTransport.importantComment、それ以外の必要な補足はTrip.summary等に対象を明記する。専用fieldが必要な実用途が判明した場合はSchemaと利用側を同じ変更範囲で検討する。

## 生成品質の確認

以下はSchemaの必須条件を追加するものではなく、新規生成・既存Trip再生成で使う内容確認である。CAL Validationに通ることと、使いやすい旅程であることは別に確認する。「埋めるべき」は確認できる情報を調べて入れる方針であり、不明値を創作して全欄を埋める意味ではない。

### 内容を判断する原則

| 原則 | 生成時の判断・確認 |
| --- | --- |
| 意味・効力の範囲に置く | 情報はその意味・効力が成立する日／予定にだけ配置し、別日へ先取り・持ち越し・重複しない。対象期間のある条件と、特定時点の行動を区別する。例えば宿泊やレンタカーの開始・終了条件は、それぞれが成立する日の該当予定に対応させる |
| 情報の所有箇所を一つにする | 同一情報は最も適切な所有箇所へ一度だけ置く。予約に属する情報は既存の適切な予約情報欄へ集約し、通常コメント・重要コメント・補足へ重複記載しない。予約・宿泊・移動等に関連する予定が複数あっても、共通情報を各予定のコメントへ複製せず、既存の参照で共有する。予約に属する情報と予定・施設固有の情報は前節の格納先に分け、通常コメントと重要コメントにも同じ内容を重ねない。例えば宿泊予約の条件はBooking.notesに置き、同じ宿での夕食等の別予定には、その予定固有の補足だけを書く |
| 構造と説明を分ける | 構造化フィールドで表現済みの情報を説明文へ重複させず、説明文にはそこで分からない判断条件・補足だけを書く。候補名の列挙や時刻・金額の再掲でコメントを埋めない。自然な予定本文に採用済みPlace名を含める契約は維持する。予約前の備忘・検討事項は原則として旅程表示用コメントへ入れない。金額は必要に応じてBooking.amount / currency等の所定の構造化fieldへ保持し、通常コメント・重要コメント・補足説明（summary / details / Booking.notes等）には原則記載しない。確認済み金額は構造化fieldで保持し、不明な金額を創作しない |
| 短く読めるコメントにする | コメントは利用に必要な情報だけを簡潔に書く。自然文は意味が損なわれない範囲で短句・体言止めを優先し、不要な句点を省く。情報がない欄を説明文で埋めない |
| 独立した概念を混同しない | statusは行動自体の実施判断（決定済みconfirmed、提案・仮置きtentative、実施するか未定undecided）、timeは時刻の表現、Booking.statusは確認できた予約事実、selectionは明示された場所の採用を表す。一つの確定から他の確定を推測しない。実施確定でも時刻や場所は未定にでき、時刻不要と時刻未定も区別する。候補は1件でも未採用ならselection=[]とする |
| 確認済みの事実を使い、変更範囲を守る | 外部情報は対象の同一性と根拠を確認できた値だけを入れ、不明値・予約事実を創作しない。再生成でも既存対象のID、明示採用済みPlace、予約事実、未変更部分を保持する。変更によって情報の効力が変わる場合は再確認し、利用に必要な不足・未解決事項だけ短く返す |
| 行動の単位を揃える | 同じ行動の言い換えや、一続きの行動を冗長に分割した項目はまとめ、残すIDと必要な候補・コメント・参照を保持する。別の行動や明示された別行動は時刻が重なるだけで統合しない。実際の時間衝突は勝手な時刻変更で隠さず、未解決事項として返す。移動はTransportに集約する |

### 原則を既存fieldへ適用する

以下は格納・参照上の補足であり、個別の旅行に限る例外ルールではない。

| 対象 | 対応・確認 |
| --- | --- |
| 日別代表エリアと座標 | Day.areasは行動順の主要エリアを表し、routeSummaryと一致させる。各nameの代表地点を地域・住所で照合し、確認できたlatitude / longitudeをlocationへ両方入れる。広域名なら代表地点が分かるnameにする。未確認ならlocation=nullとし、必要な未取得地点を返す。別地点の座標で代用せず、Place.locationとDay.areasはそれぞれの対象を表す |
| 予約の対象と参照 | 移動予約はBooking.transportIdと対象Transport.bookingIdを対応させ、targetDateをその移動日にする。宿泊・施設予約はBooking.placeIdを実際の対象へ結び、該当予定のselectionとの対応を確認する。ScheduleItemにbookingIdを追加しない。対象不明の参照は許されるnullのままにし、表示目的で未採用候補を選んだり、予約不要の移動へBookingを作ったりしない |
| 一つの予約が複数対象を含む場合 | BookingのtransportId / targetDateは各1件なので、複数区間は対象ごとのBookingと各Transport.bookingIdに整理する。同一予約に含まれることはnotesに記す。総額しか分からなければ区間金額を創作・重複計上せず、一方のamountに確認済み総額を保持し、他方はamount=nullとする。対象範囲だけをnotesへ記し、金額を再掲しない。bookedは確認できた対象範囲に限る。複数泊の対象日・期間は前節の表現に従う |

天気は座標付きDay.areasを使い、予定Placeや移動端点から自動選択しない。予報値はTrip JSONへ書き込まずCALが取得する。座標があっても予報期間外・取得不可なら表示されない。表示・取得の詳細は[旅程詳細モデル](trip-detail-model.md#閲覧編集の意味境界116)を参照する。

生成後は上記原則に沿って内容を一度通して確認し、日別の行動順・時刻、情報の適用範囲・所有箇所、代表エリアと予約の参照が整合することを確かめる。Schema / validatorは構造・既存の意味整合を担当し、これらの品質判断を一律の拒否条件にしない。

## 受渡しとCAL採用の境界

| 場所 | 役割 |
| --- | --- |
| Calendar Git / Calendar_GD | Schema・guideの正本 / 公式参照コピー |
| Google Drive上の `Calendar_Chat/<trip-id>/candidate.json` | cloud Chatから渡す新規Tripの未採用complete JSON本体（Envelopeなし）。再生成で同じファイルを更新してよく、履歴管理を追加しない |
| `/Users/us/Tools/GoogleDrive/Calendar_Chat/<trip-id>/candidate.json` | Mac上で同期された同じcandidate。local ChatとCALが参照する |
| Calendar_Local | CALで採用後の正式TripとSQLite等の通常状態。Chatから直接書き換えない |
| `Calendar_Chat/<trip-id>/` | 新規・既存Trip共通の授受先。既存TripのcontextはCAL所有、candidateはChat所有のEnvelope。Calendar_GDとは分ける |

cloud Chatが接続中のGoogle Drive上の受渡しフォルダへ保存できない場合のみ、その旨を示して`candidate.json`を添付し、対象の`<trip-id>/`への配置をusに依頼する。Macローカルパスへ保存できたと主張したり、Calendar_GDやCalendar_Localを代わりに使ったりしない。新規Tripは明示的な取込操作で採用する。

正式なSchema・semantic ValidationはCALの新規Trip取込が担当する。Frame `/calendar/import` で共有candidateを選ぶとCALが読込・Validationし、エラーならcandidateを修正して再確認する。Chat側の自己確認や別環境での検証をCAL Validation PASSの代わりにしない。

Issue #110で[新規JSON取込](trip-json-import.md)へ接続した。Frameで共有candidateを選び、Validation結果と内容を確認して新規登録する。既存Tripは同じIDで置換しない。日本語ラベルの全Trip補正UIは置き換え、1予定追加コピペは維持する。

## 北海道4日間の代表例と内容確認

[代表JSON](../Samples/hokkaido-4days-candidate.json)は、2027-06-12〜15を仮の日程とした公開施設ベースの合成例。実旅行・実予約・usの採用済み希望ではない。出典と確認内容は[Samples README](../Samples/README.md)を参照する。

札幌を拠点に、到着日、小樽日帰り、札幌市内、帰路の順とし、遠距離の詰込みを避ける。3泊、往復の主要鉄道移動、候補未選択、店未定、住所・URL・座標・コメント・pending予約を含む。時刻は未定とし、将来ダイヤや空室を保証しない。候補訪問時の市内移動は訪問先選択後に決める。

Schemaで今回必要な情報を表現できるため変更は不要。Validationとは別に、日程と対象日、宿泊回数、往復経路、候補の非採用、未定値、参照の整合、行動・移動・コメントの重複がないことを確認する。料金、営業日、予約、交通ダイヤは実旅行決定時に再確認する。

## 新規Trip主要経路の最終確認（#126）

[代表入力と出典](../Samples/README.md#新規trip主要経路の最終確認126)から生成した[complete JSON](../Samples/hokkaido-import-review.json)を使う。確定Placeを含む本文、未選択の複数候補、3泊、重要 / コネクタ移動、fixed / range / undecided、booked / pendingを含む。日時とbookedは明示した合成入力であり、実旅行・実予約を意味しない。

このcandidateを一時受渡し先に置き、Frame `/calendar/import` で読込・Validation・内容確認・新規登録し、通常旅程で候補正式採用と本文・時刻・コメントの直接編集を確認する。テストではDB・Trip root・Chat root・candidate rootをすべて一時環境へ明示する。Calendar_Localや運用共有先には保存しない。

## 既存Tripの変更

新規Trip取込は既存Tripの上書き経路ではない。既存Tripの主要なChat往復は[継続するChat往復](#継続するchat往復112)の共有Envelopeを使う。既存Working exportとAI InstructionのJSON Patch経路も保持する。いずれもCALがValidationと正式採用を担当し、Chatは正式ファイルを直接置換しない。

### 再生成の使い分け

| 状態・変更 | 使う経路 |
| --- | --- |
| 登録前 | 同じTrip IDのcomplete JSON本体を同じcandidate.jsonへ何度でも再生成し、CALで再度Validation・内容確認してからImportする |
| 登録後の局所変更 | 時刻・予定・コメント等はCALの直接編集、または最新contextを基にした既存Trip用candidate Envelopeで変更する。Chatへ局所変更を頼む場合も返すtripはcomplete JSON |
| 登録後の全体再生成 | 宿泊地・日数・日別構成等を大きく組み直す場合も最新contextのeffective Tripを出発点に、変更範囲を指示してEnvelope内のcomplete Tripを再生成する。既存対象のID・予約事実・変更対象外の内容を保持する。同じTripの更新に新規Importを使わない |
| 開始日入りTrip IDで日程変更 | 開始日が変わりIDも新日程に合わせる運用では、新しいTrip IDと同名フォルダへcomplete JSON本体を作り、新TripとしてImportする。旧TripのIDやフォルダだけを変更して更新扱いにしない。旧Tripの整理・削除は別途usの指示で扱う |

Trip IDに日付を含めることや、開始日変更時のID変更はSchema上の必須条件ではない。上表は日付入りIDと日程を一致させる場合の再作成運用であり、自動リネーム・自動移行は追加しない。新日程では予約の有効性、交通日時、営業日等を見直し、旧予約を新日程で有効なbookedへ機械的に移さない。

既存Tripのcandidateは通常表示・再読込で検証後に自動反映される。全体再生成でも別の確認画面はないため、変更意図を整理してから受渡し先へ保存する。base_revisionを手で現在値へ付け替えず、staleなら最新contextから作り直す。受渡し・採用の詳細は[継続するChat往復](#継続するchat往復112)を正本とする。

## 実利用からガイドを更新する

1. 実旅行で不足を見つけたら、短いCalendar Issueに「困った表示・生成結果」「期待する内容」「一般化できる生成ルール」を記す。実Trip本文や予約情報を転記せず、必要なら架空の短い例で示す。
2. 現行mainの本ガイド・Schema・関係する表示/Validation契約を確認する。既存fieldで表せる生成品質は、本ガイドの該当箇所を修正・統合する。旅行ごとの例外一覧や別チェックリストを増やさない。Schemaで表せない実用途やCAL自体の不具合だけを、別の変更範囲として検討する。
3. 文書変更は契約との内容照合と差分検査を最小確認とし、例JSONを変更した場合だけそのJSONも検証する。現行TDSに従いPR・merge・Calendar_GD公式同期・Issue closeまで進める。変更理由と確認結果はIssue / PRに残し、ガイドには現行ルールを残す。

以後の生成は冒頭の現行正本読取りで更新を取り込む。既存の実Tripへは遡及適用せず、修正が必要なTripは別途依頼されたときに通常の変更経路で扱う。

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

Place.officialUrlは確認済み公式リンク、urlsは参考リンク。本文actionは「すし善で夕食」のような自然文を保持し、施設名をPlace.nameと一致させる。レストラン候補で食べログURLを取得できた場合は、取得できる範囲で既存rating（source=食べログ、observedAt付き）も設定し、点数を取得できない場合のみnullとする。確認済みの値だけを記し、推測しない。

予定単位の `ai_instruction` はCALの既存 `ai_instructions` に保存する別データである。
予定本文・summary・details・Booking.notesへ混在させず、complete Trip JSONのコメントとして転記しない。
