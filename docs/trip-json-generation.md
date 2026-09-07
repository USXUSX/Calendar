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
4. UTF-8の `<trip-id>.json` として受渡し場所へ保存する。ファイル中はJSONオブジェクトだけ。取得元URL・確認日が必要な情報は既存のsummary / details / urls等に短く記し、独自fieldや取得本文を足さない。
5. CAL validatorを実行可能なら実行し、エラーの箇所を修正して同じ完全JSONを更新する。Chat側で実行できなければ「CAL Validation未実行」と伝え、合格を装わない。
6. 日別の行動順・移動・宿泊・候補・未定事項を内容確認し、candidateを渡す。Validation成功だけで正式採用しない。

短い生成指示：

> 現行mainのSchemaとこのガイドを読み、Calendarの正式スキーマに一致する完全な旅行JSONを1個生成してください。ファイル中にはMarkdownや説明文は付けません。確認できた候補・URL・住所・座標・コメントを含め、不明値や予約事実を創作しません。候補は自動選択しません。`<trip-id>.json`を指定の受渡し場所へ保存し、検証結果と残る未定事項を別に短く伝えてください。

## 項目と不明値

キー・型・enumの詳細はSchemaを正本とし、ここでは生成時の使い分けを定める。必須キーは省略しない。任意情報はSchemaが許す`null`または空配列を使う。`searchQuery`は条件がある場合だけ付ける。

| 内容 | 格納先・使い分け |
| --- | --- |
| 旅行全体と日別 | Tripのtitle / dateRange / summary、Dayのdate / title / routeSummary。titleは短いテーマ、routeSummaryは代表エリア・主経路 |
| 行動 | ScheduleItem.action / category。場所名や時刻をactionへ重複させず、移動はTransportだけにする |
| 候補と採用場所 | Placeを1地点1件にしてcandidatePlaceIdsで参照。selectionは明示された採用場所だけ。1候補でも未採用なら空配列 |
| 場所未定 | candidatePlaceIdsとselectionを空配列、非空searchQueryに元条件、minSelections / maxSelectionsはnull。架空の「未定」というPlaceは作らない |
| 地点情報 | Place.name / category / address / location / urls / rating。未確認の住所・座標・評価はnull、URLは空配列。locationがある場合は緯度経度の両方が必要 |
| コメント | 通常コメントはScheduleItem.summary、追加事実・出典等はdetails、施設自体の補足はPlace.summary。重複させない |
| 時刻 | fixedは開始必須、rangeは開始・終了必須、undecidedは開始・終了null。所要時間不明はdurationMinutes=null。列車の発着時刻と提案枠を混同しない |
| 移動 | TransportでdayId、両端Place、mode、timeを持ち、Day.transportIdsから参照する。未確認の所要時間を確定値にしない |
| 予約 | BookingをplaceIdまたはtransportIdへ結ぶ。targetDateは対象日。未予約の予定はpending、実際に予約した証拠がある場合だけbooked。金額不明はnull、予約条件はnotes |
| 準備・Rio | preparation / rioPlanも必須。準備がなければtasks=[]。Rioが対象外と分かる場合だけapplicable=false / careMode=not_applicable。不明ならundecidedとして判断を残す |

候補数は新規Trip JSON全体に一律3件制限を置かない。既存予定へのAFM候補追加の件数制限とは別契約である。minSelections / maxSelectionsは分かる場合だけ設定し、最大数は候補件数以内にする。

IDはSchemaに従う英数字・ハイフン・アンダースコアを使い、同じcandidateの再生成では既存対象のIDを維持する。ScheduleItem.dayIdは親Dayと一致させ、日内orderはScheduleItemとTransportを合わせて重複させない。selectionはcandidatePlaceIdsの部分集合にする。移動のdayIdとDay.transportIds、予約の対象参照と日付を対応させ、参照漏れや不要なPlaceを残さない。

日跨ぎ時刻、未確定の移動端点など、現在のSchemaでそのまま表現できない入力は、事実を偽装して通さず不足を伝える。予約済みの複数泊は開始日をtargetDateとし、チェックアウト日等の条件をnotesへ記す。移動への任意コメントfieldはないため、予約条件はBooking.notes、それ以外の必要な補足はTrip.summary等に対象を明記する。専用fieldが必要な実用途が判明した場合はSchemaと利用側を同じ変更範囲で検討する。

## 受渡しとCAL採用の境界

| 場所 | 役割 |
| --- | --- |
| Calendar Git / Calendar_GD | Schema・guideの正本 / 公式参照コピー |
| `/Users/us/マイドライブ/ChatGPT共有/CAL/<trip-id>.json` | 未採用candidateの作業ファイル。再生成で同じファイルを更新してよく、履歴管理を追加しない |
| Calendar_Local | CALで採用後の正式Tripと通常状態。Chatから直接書き換えない |

受渡しフォルダへアクセスできないChatは、同名JSONを添付してusに配置を依頼する。保存できたと主張したり、Calendar_GDやCalendar_Localを代わりに使ったりしない。受渡し場所は自動監視・自動取込の入口ではない。

Git正本で次を実行する。このCLIはSchemaとsemantic validationを両方行い、保存状態を変更しない。

```sh
python3 scripts/validate_trip.py '/Users/us/マイドライブ/ChatGPT共有/CAL/<trip-id>.json'
```

エラーがあれば該当パスとエラーだけをChatへ返し、部分パッチではなく同じcomplete JSONを直す。CALの取込操作がValidation・内容確認・正式採用を担当する。Chatが検証済みファイルをCalendar_Localへコピーする運用にはしない。

Issue #108時点では新規complete JSON向け取込UI / commandの整備は次Stepである。現行`parse_chat_paste`等は日本語ラベル入力用であり、JSON対応済みと扱わない。次Stepはcandidateを読み、CAL所有のSchema / semantic Validation、新規Trip確認、通常の初回採用境界へ接続する。既存Tripを同じIDで置換しない。日本語ラベル経路の存廃はそこで利用価値から判断し、1予定追加コピペの廃止と混同しない。

## 北海道4日間の代表例と内容確認

[代表JSON](../Samples/hokkaido-4days-candidate.json)は、2027-06-12〜15を仮の日程とした公開施設ベースの合成例。実旅行・実予約・usの採用済み希望ではない。出典と確認内容は[Samples README](../Samples/README.md)を参照する。

札幌を拠点に、到着日、小樽日帰り、札幌市内、帰路の順とし、遠距離の詰込みを避ける。3泊、往復の主要鉄道移動、候補未選択、店未定、住所・URL・座標・コメント・pending予約を含む。時刻は未定とし、将来ダイヤや空室を保証しない。候補訪問時の市内移動は訪問先選択後に決める。

Schemaで今回必要な情報を表現できるため変更は不要。Validationとは別に、日程と対象日、宿泊回数、往復経路、候補の非採用、未定値、参照の整合、行動・移動・コメントの重複がないことを確認する。料金、営業日、予約、交通ダイヤは実旅行決定時に再確認する。

## 既存Tripの変更

本書の新規Trip生成は既存Tripの上書き経路ではない。Working exportからのcomplete candidateは既存Phase 5のValidation / stale gate / atomic adoptionを通す。AI InstructionのCAL claim経路はbase version/hashに対するJSON Patchを使う。両経路ともChatによる正式ファイルの直接置換は行わない。
