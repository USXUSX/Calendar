# Chat向け完全Trip JSON生成ガイド

新規Tripの主要経路は **Chatで完成度の高いcomplete Trip JSONを生成 → CALでValidation・内容確認・取込** とする（Issue #108）。既存Tripへの1予定追加のコピペとは別経路である。取込後のCAL編集は微修正に限定しない。

本書はCAL旅程の共通作成ルールと登録前内容チェックの正本。別プロジェクト・別担当のChat / Codexも、CAL向け旅程を作成・再生成するときは本書を参照する。利用側のスキルやテンプレートにはルールを複製せず、GitHub現行mainの本書への参照を置く。

## 現行正本を読む

CAL用JSON作成を依頼されたChatは、毎回GitHub現行mainの次の2文書を読む。会話に残った旧Schemaや記憶だけで生成しない。

- [formal Schema](https://github.com/USXUSX/Calendar/blob/main/Schemas/trip.schema.json)
- [このgeneration guide](https://github.com/USXUSX/Calendar/blob/main/docs/trip-json-generation.md)

Gitが正本で、`Calendar_GD`はmerge後の公式共有コピー。GitHubを読めない場合は、現行mainと一致すると確認された共有コピー、またはusから渡された現行2文書を使う。現行性を確認できなければ生成を確定せず、その不足を伝える。

## 生成手順

1. 旅行名・日付・希望・確定済みの訪問先や予約を読む。必須の日付等が不明ならusに確認する。実旅行の日時・予約を創作しない。鉄道の参考時刻は下記の共通作成ルールに従い、予約事実と分ける。
2. 希望に合う少数の場所を調べ、同名施設を住所・地域で照合する。公式情報や保存可能な公開データから、確認できるURL・住所・座標・短いコメントを入れる。調べても不明な値は不明のままにする。候補は訪問確定に変えない。
3. 以下の[共通作成ルール](#共通作成ルール)・対応・意味整合と[生成品質の確認](#生成品質の確認)を使って完全JSONを1件生成する。提案した日程と予約済みの事実を区別する。
4. [登録前チェック](#登録前チェック)を済ませ、complete JSONと要求IDを[CAL専用コマンド](chat-schedule.md)へ渡す。正式ファイル・DB・共有candidateをChatが直接更新する通常経路にはしない。
5. CALのSchema・semantic Validation、revision確認、座標補完契約を通し、エラーなら内容を修正する。自己確認をCAL Validation済みとは扱わない。
6. 保存確定receiptを取得し、保存内容・対象ID・要求ID・receipt・revisionと残る未定事項を返す。応答不明時は同じ要求IDで照合する。

短い生成指示：

> 現行mainのSchemaとこのガイドを読み、Calendarの正式スキーマに一致する完全な旅行JSONを1個生成してください。ファイル中にはMarkdownや説明文は付けません。確認できた候補・URL・住所・座標・コメントを含め、不明値や予約事実を創作しません。候補は自動選択しません。保存・最終表示は上記の生成手順に従ってください。

## 共通作成ルール

### 飲食店の食べログ点数

採用済み店と未選択候補の双方で、食べログの該当店舗ページを確認し、点数を旅程で確認できるようにする。同名店は所在地で照合し、確認できた点数をPlace.rating（value / source=食べログ / observedAt=実際の確認日）、根拠の店舗URLをPlace.urlsへ保持する。他サイトの評価・検索断片の未確認値・推測値で代用しない。

点数を取得できなければrating=nullを保ち、Place.summaryに「食べログ点数未取得」と短く明示する。店舗URLも確認できなければ創作しない。未取得時の確認日・参照先・取得できなかった理由は必要な範囲で同欄に添える。値を取得できたら未取得文言を取り除く。既存CALでは点数表示がレストラン候補欄に限られるため、JSONに保持できたことと各表示箇所での点数表示確認は区別する。別形式の旅程・テンプレートでも点数・確認日・根拠、または未取得を示す。表示機能の拡張は本ガイド改訂の対象外とする。

### 行動の確定と未決事項

ScheduleItem.status / Transport.statusはその行動を行うかどうかの判断。行動が決定済みならconfirmedとし、時刻未定、未予約、複数の店候補があるという理由でtentative / undecidedへ落とさない。tentativeは行動自体の提案、undecidedは実施するか未定の場合に使う。

例えば「小樽で昼食」は実施確定、店は2候補から未選択、時刻未定ならstatus=confirmed、selection=[]、time.kind=undecidedを併用する。予約が必要でまだ予約していないならBooking.status=pending。店の選択・時刻の決定・予約済みはそれぞれ確認できた事実から設定する。

### 同行者が読む共有メモ

旅程本文・summary・details・importantComment・Booking.notesは同行者も読む共有物として、当日の行動に必要な情報を自然に書く。アクセス、営業上の注意、集合場所、選択条件などを簡潔に残す。内輪の相談事情や担当決め、AIへの指示をそのまま載せない。

例えば「店は妻が決める」は載せず、当日に必要なら「昼食は候補から選択」とする。候補欄だけで十分ならメモは空欄にする。「予約担当は妻」等の相談用メモも共有旅程へ転記せず、確認済みの予約条件だけをBooking.notesへ置く。準備タスクの担当等、正式な別用途の情報まで一律に削除する規則ではない。

### 鉄道の参考発着時刻

電車を利用する可能性が高い区間は、乗車便未決定・未予約でも実在する利用可能性の高い便を調べ、Transport.serviceNameとtimeに発着時刻を仮置きして移動時間の目安を示す。time.kind=fixed、start / endにその便の時刻、durationMinutesに確認できた所要分を入れる。fixedは具体的な時刻を持つ表現であり、便の採用や予約済みの証明ではない。移動自体が決定済みならstatus=confirmedを維持する。

未予約なら必要なBookingはpendingとし、bookedへ変えない。参考便の根拠（事業者の時刻表等のURL、確認日、適用期間）と乗車便未決定であることは、その区間を特定できるTrip.summaryへ一度だけ簡潔に記す。予約条件に属する情報はBooking.notesへ置く。列車名・各時刻・各コメントに「仮」を繰り返さない。例：「往復鉄道は現行ダイヤ参考、乗車便未決定（確認日・出典）」とし、往復で根拠が異なるなら区間を分ける。

旅行日のダイヤが発表済みなら対象日の便を使う。未発表なら現行ダイヤ等を参考と明記し、その適用期間と旅行日の運行未確認を区別する。存在しない便や将来ダイヤを創作しない。根拠ある便を取得できない場合のみtime.kind=undecidedとし、参考時刻未取得を短く伝える。日跨ぎ等を現行Schemaで表せない場合は値を偽装せず、既存の表現限界に従う。

## 新規Tripの地点情報を自動で充実する（#174）

新規complete JSONの作成時、未指定の地点情報はChatがWeb検索で調べて設定する。
地点名と旅行エリアが一致する妥当な最初の結果を採用し、結果選択・都度確認UIは設けない。
これは地点情報の同定であり、訪問候補のselectionを確定する意味ではない。
既に指定された値は保持し、同名の別地域施設や根拠のない値は採用しない。

- 住所 → Place.address、確認できた公式URL → officialUrl、短い地点説明 → summary。
- 飲食店の点数・根拠・未取得は[共通作成ルール](#飲食店の食べログ点数)に従う。
- 見つからない項目はSchemaどおりnull／空配列。推測で埋めず、取得本文や独自fieldを追加しない。
- 自宅は名称を「自宅」とする。CALに固定自宅設定があれば取込時に住所・座標が適用されるため、JSONではnullでよく、再検索しない。設定がない場合はユーザーから確認できた住所・座標だけを設定する。不明ならnullを保ち、旅行先の住所や座標で代用しない。住所のない「自宅」は自動検索せず、位置未登録となる。
- 取り込み時は従来どおりCALの座標・Google Place ID補完を使う。CAL内に汎用Web検索やクローラーを作らない。
- 既存Tripへの一括遡及適用は行わない。

明示されたエリア間移動だけTransport.showOnMap=trueを付ける。省略／falseでは描画しない。
始点・終点・移動手段は同じTransportの既存fieldを利用する。全移動への自動設定や経路形状の格納はしない。

## 項目と不明値

キー・型・enumの詳細はSchemaを正本とし、ここでは生成時の使い分けを定める。必須キーは省略しない。任意情報はSchemaが許す`null`または空配列を使う。`searchQuery`は条件がある場合だけ付ける。

| 内容 | 格納先・使い分け |
| --- | --- |
| 旅行全体と日別 | Tripのtitle / dateRange / summary、Dayのdate / title / routeSummary。titleは短いテーマ、routeSummaryは代表エリア・主経路 |
| 行動 | ScheduleItem.action / category。actionはユーザー向けの自然な予定本文。採用済み / 確定済みPlaceは名前を含める（例: `すし善で昼食`）。時刻はtime、移動はTransportだけにする |
| 候補と採用場所 | Placeを1地点1件にしてcandidatePlaceIdsで参照。selectionは明示された採用場所だけ。1候補でも未採用なら空配列。未選択の本文は `小樽で昼食` のような自然文とし、候補名の列挙と分ける |
| 場所未定 | candidatePlaceIdsとselectionを空配列、非空searchQueryに元条件、minSelections / maxSelectionsはnull。架空の「未定」というPlaceは作らない |
| 地点情報 | Place.name / category / address / location / urls / ratingと任意officialUrl。公式と確認済みのURLだけofficialUrlへ設定する。未確認の住所・座標・評価はnull、URLは空配列。locationがある場合は緯度経度の両方が必要 |
| コメント | 通常コメントはScheduleItem.summary、追加事実・出典等はdetails、施設自体の補足はPlace.summary。予定の重要コメントは予約の有無によらずScheduleItem.importantComment。予約番号・取消条件・予約上の連絡事項等はBooking.notesに保持し、予定の重要コメントへ自動展開しない。Transportの予約に属さない重要コメントは任意importantComment。情報の所有箇所に置き、他へ複製しない |
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
| 情報の所有箇所を一つにする | 同一情報は最も適切な所有箇所へ一度だけ置く。予約に属する情報は既存の適切な予約情報欄へ集約し、通常コメント・重要コメント・補足へ重複記載しない。予約・宿泊・移動等に関連する予定が複数あっても、共通の予約情報を各予定のコメントへ複製せず、Bookingに保持する。予定の重要コメントは予定ごとに独立させる。予約に属する情報と予定・施設固有の情報は前節の格納先に分け、通常コメントと重要コメントにも同じ内容を重ねない。例えば宿泊予約の条件はBooking.notesに置き、同じ宿での夕食等の別予定には、その予定固有の補足だけを書く |
| 構造と説明を分ける | 構造化フィールドで表現済みの情報を説明文へ重複させず、説明文にはそこで分からない判断条件・補足だけを書く。候補名の列挙や時刻・金額の再掲でコメントを埋めない。自然な予定本文に採用済みPlace名を含める契約は維持する。予約前の備忘・検討事項は原則として旅程表示用コメントへ入れない。金額は必要に応じてBooking.amount / currency等の所定の構造化fieldへ保持し、通常コメント・重要コメント・補足説明（summary / details / Booking.notes等）には原則記載しない。確認済み金額は構造化fieldで保持し、不明な金額を創作しない |
| 短く読めるコメントにする | コメントは利用に必要な情報だけを簡潔に書く。自然文は意味が損なわれない範囲で短句・体言止めを優先し、不要な句点を省く。情報がない欄を説明文で埋めない |
| 独立した概念を混同しない | statusは行動自体の実施判断（決定済みconfirmed、行動自体の提案tentative、実施するか未定undecided）、timeは時刻の表現、Booking.statusは確認できた予約事実、selectionは明示された場所の採用を表す。一つの確定から他の確定を推測しない。実施確定でも時刻や場所は未定にでき、時刻不要と時刻未定も区別する。候補は1件でも未採用ならselection=[]とする |
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

## 登録前チェック

新規create・既存save・手動JSON取込の前に、生成者が次を内容確認する。Schema / semantic Validationとは別の確認であり、新たな機械的拒否条件は追加しない。共通作成ルールの格納先と判断を使い、未取得・未決事項は短く報告する。

- 飲食店の採用済み店・候補に食べログ点数、実際の確認日、該当店舗URLがあるか。取得できなかった店はrating=nullと未取得の明示があり、点数や根拠を捏造していないか。渡す旅程・表示対象で点数または未取得が読み取れるか。
- 行動が確定している予定・移動はconfirmedか。未予約・時刻未定・候補複数を理由に未確定扱いにしていないか。time、Booking.status、selectionは各事実に対応しているか。
- メモを同行者の視点で読み、当日必要な情報になっているか。内輪の相談・担当決め・AI指示、構造化情報の不要な再掲が残っていないか。
- 利用可能性の高い鉄道区間に実在便の発着時刻と所要時間の目安があるか。出典・確認日・適用ダイヤ、乗車便未決定と予約状態を区別し、未来ダイヤ未発表を現行参考と明示しているか。「仮」を各所へ重複していないか。時刻未取得やSchemaの表現限界は明示しているか。
- 日付・行動順・参照・予約対象・情報の所有箇所が整合し、既存更新ではID・予約事実・選択済み地点・変更対象外の内容を保持しているか。

## 受渡しとCAL採用の境界

通常Chatは既存RDC＋[CAL専用コマンド](chat-schedule.md)に統一する。Git/Calendar_GDは仕様の正本/参照、Calendar_LocalはCALが保存する正式JSON・SQLite、Calendar_Chatは旧授受ファイルと手動新規取込候補の保持先である。Driveへcandidateを書いたことを正式保存とはしない。

既存のFrame `/calendar/import`による手動新規取込は維持するが、Chatの通常経路はcreate/save＋receiptとする。残存context/candidateを削除・自動採用しない。直接接続不能時は正式保存できていないと報告し、別経路の自動採用へ迂回しない。

## 北海道4日間の代表例と内容確認

[代表JSON](../Samples/hokkaido-4days-candidate.json)は、2027-06-12〜15を仮の日程とした公開施設ベースの合成例。実旅行・実予約・usの採用済み希望ではない。出典と確認内容は[Samples README](../Samples/README.md)を参照する。

札幌を拠点に、到着日、小樽日帰り、札幌市内、帰路の順とし、遠距離の詰込みを避ける。3泊、往復の主要鉄道移動、候補未選択、店未定、住所・URL・座標・コメント・pending予約を含む。この旧合成例は参考便取得前のため時刻未定を保持している。新規作成の鉄道は上記の参考発着時刻ルールに従う。将来ダイヤや空室を保証しない。候補訪問時の市内移動は訪問先選択後に決める。

Schemaで今回必要な情報を表現できるため変更は不要。Validationとは別に、日程と対象日、宿泊回数、往復経路、候補の非採用、未定値、参照の整合、行動・移動・コメントの重複がないことを確認する。料金、営業日、予約、交通ダイヤは実旅行決定時に再確認する。

## 新規Trip主要経路の最終確認（#126）

[代表入力と出典](../Samples/README.md#新規trip主要経路の最終確認126)から生成した[complete JSON](../Samples/hokkaido-import-review.json)を使う。確定Placeを含む本文、未選択の複数候補、3泊、重要 / コネクタ移動、fixed / range / undecided、booked / pendingを含む。日時とbookedは明示した合成入力であり、実旅行・実予約を意味しない。

このcandidateを一時受渡し先に置き、Frame `/calendar/import` で読込・Validation・内容確認・新規登録し、通常旅程で候補正式採用と本文・時刻・コメントの直接編集を確認する。テストではDB・Trip root・Chat root・candidate rootをすべて一時環境へ明示する。Calendar_Localや運用共有先には保存しない。

## 既存Tripの変更

新規Trip取込は既存Tripの上書き経路ではない。既存Tripの主要なChat往復は[CAL専用コマンド](chat-schedule.md)を使う。既存Working exportとAI InstructionのJSON Patch経路も保持する。いずれもCALがValidationと正式採用を担当し、Chatは正式ファイルを直接置換しない。

### 再生成の使い分け

| 状態・変更 | 使う経路 |
| --- | --- |
| 登録前 | complete JSONを生成し、CAL専用コマンドのcreateで新規登録する |
| 登録後の局所変更 | 時刻・予定・コメント等はCALの直接編集、または最新trip-getを基にしたsave要求で変更する。Chatへ局所変更を頼む場合も返すtripはcomplete JSON |
| 登録後の全体再生成 | 宿泊地・日数・日別構成等を大きく組み直す場合も最新trip-getのeffective Tripを出発点に、変更範囲を指示してsave要求のcomplete Tripを再生成する。既存対象のID・予約事実・変更対象外の内容を保持する。同じTripの更新に新規Importを使わない |
| 開始日入りTrip IDで日程変更 | 開始日が変わりIDも新日程に合わせる運用では、新しいTrip IDのcomplete JSON本体を作り、createで新規登録する。旧TripのIDやフォルダだけを変更して更新扱いにしない。旧Tripの整理・削除は別途usの指示で扱う |

Trip IDに日付を含めることや、開始日変更時のID変更はSchema上の必須条件ではない。上表は日付入りIDと日程を一致させる場合の再作成運用であり、自動リネーム・自動移行は追加しない。新日程では予約の有効性、交通日時、営業日等を見直し、旧予約を新日程で有効なbookedへ機械的に移さない。

更新は最新取得のrevisionをそのまま指定する。staleなら最新trip-getから変更意図を適用し直し、revisionだけを付け替えない。保存・照合の正本は[正式Chatコマンド](chat-schedule.md)。

## 実利用からガイドを更新する

1. 実旅行で不足を見つけたら、短いCalendar Issueに「困った表示・生成結果」「期待する内容」「一般化できる生成ルール」を記す。実Trip本文や予約情報を転記せず、必要なら架空の短い例で示す。
2. 現行mainの本ガイド・Schema・関係する表示/Validation契約を確認する。既存fieldで表せる生成品質は、本ガイドの該当箇所を修正・統合する。旅行ごとの例外一覧や別チェックリストを増やさない。Schemaで表せない実用途やCAL自体の不具合だけを、別の変更範囲として検討する。
3. 文書変更は契約との内容照合と差分検査を最小確認とし、例JSONを変更した場合だけそのJSONも検証する。現行TDSに従いPR・merge・Calendar_GD公式同期・Issue closeまで進める。変更理由と確認結果はIssue / PRに残し、ガイドには現行ルールを残す。

以後の生成は冒頭の現行正本読取りで更新を取り込む。既存の実Tripへは遡及適用せず、修正が必要なTripは別途依頼されたときに通常の変更経路で扱う。

## 継続するChat往復（#112）

#205で通常経路をRDC専用コマンドへ置換した。trip-getはeffective complete Tripと指示を返す。変更対象外の値、既存ID、予約事実、採用済み地点を保持し、対応した指示だけをhandled_instruction_idsへ指定する。Direct Overrideは検証後の採用transactionで吸収し、未対応指示とWorkingは保持する。形式・競合・中断復旧・receiptは[正式Chatコマンド](chat-schedule.md)が正本。

旧Envelopeのreview/adoptと明示context exportは保守用domain機能として保持するが、通常ChatやFrame loadから呼ばない。get_chat_contextは通常メモリ上の値を返し、明示publish=Trueだけが旧contextを出力する。残存candidateは勝手に採用・削除しない。FrameのChat指示入力は継続し、workerは起動しない。

### #116の編集情報

contextのTripには任意のDay.areas（順序付きname/location）、ScheduleItem.candidateJudgments、
Transport.serviceNameとmode=shinkansenを保持できる。予約不要でも旅程上重要な移動は任意booleanのimportantで保持する（省略時false）。予約済み・予約予定は既存Bookingを使う。詳細は[表示・更新契約](trip-detail-model.md#通常旅程とインライン編集119--121)。rangeは開始＋durationMinutesから終了を計算する。
予定単位instructionsはsource_item_idを持つ。Chatは対象を解決して結果をcandidateへ反映し、
対応済みのIDをhandled_instruction_idsへ列挙する。指示文自体を予定本文に転記しない。

Place.officialUrlは確認済み公式リンク、urlsは参考リンク。本文actionは「すし善で夕食」のような自然文を保持し、施設名をPlace.nameと一致させる。飲食店の点数・根拠・未取得は[共通作成ルール](#飲食店の食べログ点数)に従う。

予定単位の `ai_instruction` はCALの既存 `ai_instructions` に保存する別データである。
予定本文・summary・details・Booking.notesへ混在させず、complete Trip JSONのコメントとして転記しない。

座標がない地図対象は専用コマンドまたは手動Frame取込で[座標補完契約](map-locations.md)に従って補完する。既存Tripの保存済み座標は保持する。

### 訪問先と内部の食事候補（#167追加修正）

「市場へ行く」と「市場内で食べる」は別の予定にする。市場自体のPlaceを訪問予定のselectionへ設定し、食事予定には店A・店BをcandidatePlaceIds、selection=[]として入れる。概要の訪問先は市場、候補を比較するときの地点は個々の店となる。市場へ行く予定を店候補の集合だけで代用しない。候補名・座標は各店のものを保持する。

同じ考え方を施設内の候補にも使う。地図で曖昧な親子関係を推測したり、候補を自動採用したりしない。現在の旅程をこの規則で自動再構成するものではない。既存のmapPlaceIdは明示された表示先指定として扱う。

PlaceとDay.areasの任意googlePlaceIdは、Google Placesで実際に取得したIDがある場合だけlocationと組にして保持する。創作せず、位置未登録は[共通地点取得](map-locations.md)へ渡す。既存座標・手動補正は自動上書きしない。

写真連携を使うTripには任意の`photoAlbumName`を指定する。既存の通常アルバムの命名規則
`yyyy-mm-dd_場所`に従った承認済みの名前を保持し、Trip表示名で置換しない。
未指定時は写真リンクを表示しない。[写真参照契約](trip-photos.md)を参照。

## 旅行管理への接続（#221）

complete Trip生成前に[Chat専用CLI](chat-schedule.md)のtravelsで既存旅行を確認する。旅行があればそのIDをTrip.idに使い、createで旅程を接続する。該当がなければ新規旅程登録と共に旅行管理を作成する。名称・期間・日程状態・主要移動手段はCAL旅行基本情報を正本とし、旅程表示に反映する。日付未定の旅行に仮旅程を作る必要はない。
