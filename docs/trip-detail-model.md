# 旅程詳細表示・更新契約

> Issue #86の現行Goal 1と貼付・外部取得方針は[初期リリース仕様](initial-release.md)に従う。本書の既存AI再生成契約は保持するが、初期リリースの完成条件ではない。

> **Status:** Issue #64 Goal 1 / Phase 2で確定。Phase 1の
> [`trip-detail-ui.md`](trip-detail-ui.md) を構成するCAL側の意味境界である。

## 正本と表示モデル

旅程詳細表示モデルは、formal Trip JSONへactive Direct Overrideを適用した
`effective Trip`から毎回派生する。表示モデル自体を保存せず、SQLiteやTrip JSONと
並ぶ正本にしない。FRM等の画面は物理schemaやTrip JSON配置を参照せず、この意味境界を
利用する。

| UI情報 | 取得元・導出 |
| --- | --- |
| 日付、主題、移動概要 | `Day.date / areas`。areas未登録の日は旧routeSummaryを表示 |
| 時刻 | `TimeSpec`。`undecided`は「未定」、`range`は開始＋滞在時間 |
| カテゴリー | `ScheduleItem.category`。移動は`transport`として派生 |
| 本文、場所link | `action`と`Place`参照。移動は出発地・到着地から派生 |
| 通常コメント | `ScheduleItem.summary` |
| 重要コメント | 対象PlaceまたはTransportに紐づく`Booking.notes`。重要性を推測して`details`を昇格しない |
| 補足事実 | `ScheduleItem.details`。重要コメントとは別に保持する |
| 天気 | Trip正本にはない。取得側が日ID単位のContextとして明示的に渡し、未取得・失敗時は`null` |
| カテゴリーicon | categoryから安定した意味keyへ変換する。具体iconはUI実装時に決める |

`scheduleItem`と`transport`の状態はTrip内容に保持する明示値
`confirmed / tentative / undecided`をそのまま返す。時刻、場所、候補数から導出せず、
通常表示ではconfirmedにラベルを付けず、tentative / undecidedだけ「未確定」とする。場所を選択しても予定状態は変更しない。候補が複数あれば`has_candidates`を独立して返し、
状態を上書きしない。

`候補あり`と候補一覧は`candidatePlaceIds`から導出する。採用済みの選択は`selection`として
区別し、候補判断の「いいね」をそこへ書き込まない。

## 閲覧・編集の意味境界（#116）

通常画面の候補「いいね」は`ScheduleItem.candidateJudgments`（Place ID → `ok`）として
Direct Overrideへ保存する。未判断はキーなし。選択・状態は変えない。
候補行の正式採用は`adopt_place_id: place_id`で選択と本文を一括保存する。旧ng値は保持できるが判断UIには表示しない。

`edit_trip_item`は状態・時刻・予定本文・コメント・`category`（観光/食事/宿泊/その他）に加え、`duration_minutes`、
`place`（名前と確認済み住所・location・urls）、`candidate_judgments`、`ai_instruction`を扱う。
移動は`from_place / to_place / transport_mode / service_name / important`を編集できる。
Transport.importantは予約不要でも旅程上重要な移動を表す任意boolean（省略時false）。
表示モデルはimportantと、bookingIdが参照するBooking.statusをbooking_statusとして返す。
予約済みbooked・予約予定pending・予約変更を要するchange_requiredは通常予定と同格、
それ以外はimportantがtrueの場合だけ同格とし、通常の移動は補助的なコネクタ表示にする。
表示都合の属性は保存せず、Transportとendpoint座標は維持する。
新しい場所名は新規Placeへ保存し、他予定の共有Placeを改名しない。
新規Place・項目変更・AI指示は同一transactionで保存する。不正値は部分保存しない。

#121の通常編集は`start / end / show_duration`を渡す。CALが開始空欄を`undecided`（開始・終了・滞在時間null）、
開始ありを`fixed`へ変換し、開始・終了ありかつshow_duration=trueなら2値を保持して差分（深夜跨ぎは翌日）を
`durationMinutes`へ計算し`range`にする。同時刻の滞在時間は保存エラー。終了なしではfixedとする。
通常表示は同じ時刻欄の上段に開始、下段に終了または滞在時間を置き、編集時は同一欄・同一幅で開始/終了を入力する。
時刻設定は具体的時刻 / 未定 / 設定なしを選ぶ。滞在分数入力は置かない。既存APIのtime_mode/range＋duration_minutesは互換のため保持する。

予定単位AI指示は既存`ai_instructions`へ保存し、生成requestを作らない。
`item:<trip_id>:<source_item_id>:<unique_id>`のIDで対象との関係を保持し、contextのinstructionsに
`source_item_id`を付ける。同一予定の指示変更は旧IDを取消して新しいIDで保存し、空欄保存はpendingを取消す。
同一内容の再保存はIDを維持する。旧指示をhandled_instruction_idsに含むcandidateは
既存のpending照合で拒否され、新しい指示を処理済みにしない。
Chatが`handled_instruction_ids`で処理完了すると通常画面の未処理表示から外れる。
予定本文やコメントへ指示そのものを残さない。後続処理は[Chat往復](trip-json-generation.md)に従う。

`edit_trip_day`は`title`を既存Day.titleの`/title`へ保存する。日付行の1日のタイトル／予定要約はこの値を使う。
正式Tripを変更せずDirect Overrideへ保存し、Workingは作成・変更しない。
同じcommandで`areas`（順序付き`{name, location}`配列）を`/areas`へ保存する。
位置不明はnull、表示は名前を矢印で結ぶ。既存のroute_summary commandは維持するが、
areasがある日はその配列を表示・天気地点の正本とする。旧文字列を自動分割しない。
日付編集は天気値を手入力せず、`lookup_place(name, adapter)`のCAL所有の取得結果から
位置を確認して使う。この読取境界は新規Placeにも共用し、保存前はsheet内だけの値とする。
保存済み・候補Placeの不足情報は既存の`get/adopt_place_enrichment`へ委譲する。

天気は順序付きareasの座標付きエリアすべてから取得し、day.weather.locationsへ順番に返す。
既存day.weather直下の最初の地点も維持する。通常表示はavailableの地点名・天気マークだけを矢印で結び、
タップで当日の全表示エリアの天気・最高最低気温・降水確率をまとめて展開し、
末尾にOpen-Meteoと取得時刻（m/d h:mm）を1回だけ表示する。予報対象外・取得不可は通常表示しない。
予定Placeや移動endpointから地点を自動選択しない。

新規Trip作成はbaseを持たないため、完全Trip JSONのcomplete candidate Validationから
初回採用する独立経路とする。既存Tripの大きな変更もChat candidateをCALが通常load / reload時に検証・自動採用する。
Day・順序・Place・Transportのstable IDと保存座標はmap-readinessを満たす。
地図providerやroute生成はGoal 2で決め、地図用の別正本は作らない。

### 通常旅程とインライン編集（#119 / #121）

タイトルと日付・区分フィルターを一つのsticky領域とする。Chat入口はタイトル右側に控えめに置き、
旅程全体の指示入力と予定別を含むpending指示の一覧だけを開く。通常の説明、成功通知、Trip取込入口、
Chat差分preview・手動確定ボタンは旅程詳細から外す。失敗時は旅程上部へエラーを示す。

Placeの任意field `officialUrl`は確認済み公式URL（https、未確認は省略/null）。`urls`は参考リンクの配列を維持し、
順序やドメインから公式サイトを推測しない。予定本文actionを変更・分解せず、選択済みPlace.nameと完全一致する
部分だけofficialUrlへリンクする。重複Place行を作らず、移動は本文リンクなし。endpointのstable ID・座標は保持する。
Wikidata P856から取得した公式URLは、既存の明示施設確認・不足値採用でofficialUrlへ保存できる。
レストラン候補のみurls中の食べログURLと、source=食べログかつ確認日を持つ既存rating.valueを表示する。
評価を再取得・推測しない。未確認の点数は空欄。候補コメントはPlace.summary。

通常は編集モードOFF。右上の鉛筆はChat指示欄、その隣に編集ON/OFFトグルを置く。
OFFでも候補の「いいね」はON/OFFできる。ONで行をタップすると直接インライン編集し、
入力欄以外・別行・取消では保存しないで閉じる。明示保存だけが更新commandを呼ぶ。
日別情報の編集と予定追加もインラインに揃え、日末尾の追加入口と行選択の中間状態は撤去する。
行内の予定追加は直下へ挿入する。日見出しの予定追加は既存の日末尾追加commandを使う。
時刻1列（開始/終了の2段）・区分・本文の列を通常表示と編集で共有し、コメントも本文の直下で編集する。
時刻は具体的時刻 / 未定 / 設定なしを選び、具体的時刻で開始・終了を入力する。状態は確定チェックON→confirmed、OFF→tentativeとし、
既存undecidedもUIでは未確定にまとめる。滞在時間表示は時刻入力の下のチェックで直接選ぶ。
移動の「重要な移動」は「確定」の右に置く。予定追加と変更を保存は同じ行の左右に置く。
通常予定はactionの自然文をそのまま入力し、場所/行動へ分解しない。Place補完とAI指示は補助欄を展開する。
移動は出発地→到着地の構造化入力を本文位置に置き、交通手段・便名・重要性を補う。表示用title入力は置かない。
表示本文もCALが出発地名と到着地名から「出発地 → 到着地」を導出する。既存bookingId/予約状態とendpoint座標を維持する。
候補行の「正式採用」は`edit_trip_item`へ`adopt_place_id`のみを渡す。CALがselectionとactionを一括保存する。
本文中の旧採用Place名を置換し、なければ「で」より前を採用Place名へ置換する。「で」もなければ「Place名で」を本文へ付ける。
既に採用Place名が本文にある場合は保持する。AIは使わず、生成文は通常の本文編集で調整できる。
予定の確定状態・いいね・候補集合は維持し、selectionがある予定の候補一覧は通常表示から隠す。編集モードでは再選択・選択解除ができる。
低レベルの`selection`更新は引き続き本文を変更しない。
選択ドロップダウンは置かず、候補行の2行構成を維持する。編集中に行の操作を実行しても未保存の本文変更は保存しない。
新規追加も同じ3列の新規行で本文・コメント・時刻・確定状態を編集する。挿入先は予定直下、日見出しからは日末尾。

候補1件は、番号 / 小さい「いいね」アイコン / 公式リンク名 / 食べログと点数の1行目と、
名前の下のコメントの2行目にする。OK/NGの文字ボタンは表示しない。
Transport.modeのwalk/train/shinkansen/bus/car/ferry/flight/otherは異なる固定SVGを使い、通常行とコネクタで共用する。
候補名は残り幅を優先使用し、正式採用操作は編集時の別行へ置く。
時刻はH:MM、区分アイコンは同じ線・サイズ・枠のSVGセットとし、文字ラベルを添えない。
区分は観光/食事/宿泊/移動/その他。日付はタブ、区分は角丸の弱いチップでグループ間を広く取る。
区分ごとの淡色をチップ・アイコン・通常行の左端アクセントへ共用し、状態で背景や色を変えない。
未確定だけ小さい暖色ラベルを本文の1行目横に置く。コメントは濃いグレー、フォントはゴシック系プロポーショナル。
日別タイトルを太字にし、単独のエリア列と区切りの中黒を表示せず、天気は右寄せにする。
ブラウザの通常選択・コピーで編集操作や状態文字が混入しないよう、非本文をuser-select:noneにする。
独自clipboard処理は持たない。末尾は控えめな「↑ 上に戻る」を置く。
MacとiPad mini相当の全画面・代表操作で確認し、production切替・実Trip変更・物理端末受入は別扱いとする。

以下のWorking・AI再生成契約は保存基盤の既存記録であり、#116の主要UIではない。

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

Issue #86では、以下の採用候補を保存可能な値に限定する。検索結果・取得本文・天気等の一時情報とcacheは[取得・保持方針](initial-release.md)に従い、formal Placeへ収束する値と分ける。既存の非空値を暗黙に上書きしない契約は維持する。

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
Trip生成時に作るstable Placeへ収束させる。既存の非空値を暗黙に上書きしない。
Issue #90で[共通施設取得adapterと⑥補完の通常採用](place-acquisition.md)を実装する。
stable Placeは明示確認した不足address/location/urlsだけを`adopt_place_enrichment`で
Direct Overrideへ正式採用し、effective Tripへ反映する。Workingの作成・変更・削除は行わない。
temporary itemは候補準備までとし、実行Job・UIは含めない。

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
Step 5ではValidation済みcandidateをgenerator-neutralな共通atomic adoption層へ渡す。same-filesystem stagingと
`os.replace`、digest journal、Trip version更新を既存Patch経路と共有し、Working経路だけの成功時状態更新として
対象Workingをclearする。中断recoveryはcandidateがcurrentならversion更新とWorking clearを完了し、old currentなら
Workingを保持する。active Direct Overrideと既存Patch経路のInstruction / request state遷移は変更しない。
Step 6では`export_working_trip_for_chat()`のpackageを出発点に、changed、pending_delete、temporary item、
day instructionを反映したcomplete formal Trip candidateを手動Chat返却相当として再投入し、同じ
`adopt_working_trip_candidate()`境界でatomic adoptionとWorking clearまで完了できることを合成データで確認した。
Chat/API自動送信、AI生成、FRM UIはこの確認へ含めない。

## Phase 6のAIG接続境界と最小generation state

Phase 6の最初の接続先はAIGとする。CALはAIGのprovider、model、credential、provider固有payloadを
知らず、AIGもCALのSQLite、Trip file、Working保存形式、adoption policyを知らない。FRMはCALの
semantic commandとread modelだけを使い、generation stateやcandidateの正本を保持しない。

CALからAIGへ渡すrequestは、契約version、CALが発行した`generation_id`、`trip_id`、および
`export_working_trip_for_chat()`が返す`cal.complete-trip-regeneration.v1` packageだけで構成する。
AIGは同じ`generation_id`と`trip_id`、complete formal Trip JSON object 1件だけを返す。AIG側の
request ID、provider、model、token、cost、raw応答はこのCAL semantic resultへ入れない。transport失敗は
candidateの代わりに失敗として返し、CALは安全なfailure分類だけを保持する。

CALはWorking Tripごとに最新generation 1件だけを所有する。Workingがなければ開始せず、開始時に
`generation_id`、`policy: auto | review`、AIGへ渡す既存Working export package、そのcanonicalな
`user_intent`のSHA-256 digest、captured effective revision、
`state: generating`を同じCAL transactionで固定する。activeな`generating`を別要求で上書きせず、
終端stateに対するusの再実行だけが新しいidentityで最新1件を置き換える。履歴、queue、retry count、
provider実行情報は保存しない。

Issue #80ではpolicyを「現在の採用方針」とする。formal Validation後のauto候補について、凍結effective Trip / Workingに対する限定3 rule（構造化item_changesの明示値不一致／pending_delete未反映、Trip summary変更、pending_deleteにない既存ScheduleItem / Transport削除）を評価する。field対応はstatus→status、start/end/time_mode→time.start/end/mode、ScheduleItemのtitle→action、normal_comment→summary。型・null・欠落を区別し、既存要素は(source_type, stable ID)で対応付ける。配列indexずれやDay移動を削除と誤認しない。未知の構造化field等で評価不能なら`diff_check_failed`として停止する。

rule検出時だけ、同じgenerationのpolicy=review、candidate保存、candidate_ready化を1 SQLite transactionで行う。最新generation / Working digest / current effective revision / constraintを再確認し、条件付き更新0件はConflict。DB書込み失敗は`GenerationWriteError`としてrollbackし、failedへの遷移成功と報告しない。昇格後は既存review確認へ合流し、自動採用へ継続しない。未検出autoと元reviewは既存経路を維持する。policyの自動降格、開始時policyや理由の履歴列、検査版証跡は追加しない。

本検査は全変更の意図・保持保証ではない。自由文の意図未達、未指定fieldやPlace/Day情報の変更等は検出外となり得る。正当なsummary変更もreview対象になる。既存reviewのstale候補保持・手動回復・journal recoveryは再実装しない。

最小stateは`generating / candidate_ready / failed / adopted`とする。`review`でidentityが一致する正常な
candidateを受けた場合だけcomplete candidateを`candidate_ready`に保持する。`auto`で上記rule未検出ならcandidateを
永続的な確認待ちにせず、既存`adopt_working_trip_candidate()`相当のPhase 5 Validation、captured
revision stale gate、atomic adoptionへ渡す。`review`の確定操作も保持candidateを同じPhase 5境界へ渡す。
成功時は`adopted`とadoption結果のversion / digestだけを残し、candidateをclearする。

AIG transport失敗、malformed result、Validation / semantic conflict、staleは`failed`として分類し、
authoritative TripとWorkingを変更しない。failed stateは再実行可能だが自動retryしない。staleはWorking
再編集・再export後の新しい手動生成でだけ解消し、自動rebase・自動mergeしない。生成identity不一致の
遅延resultは現行stateを変更せずConflictとして拒否する。

手動Chatの`export → 対話調整 → complete candidate → adopt_working_trip_candidate()`は独立fallbackとして
維持し、AIG generation stateを経由することを要求しない。CAL外旅行計画正本更新、production activation、
Calendar_Local migration、provider選択UI、常駐workflowはこの境界に含めない。

Step 2のCAL semantic/storage境界は`working_trip_generations`をWorking Trip用の独立した最新1行として使う。
`start_working_trip()`は確定Tripを再編集するため、現行effective revisionをbaseに空のWorkingを開始する。
既存Workingを上書きせず、前のWorkingに属する終端generationだけをclearする。FRMは空のWorking保存envelopeを
組み立てず、このcommandを編集開始に利用する。
`get_working_trip_generation()`は行がない場合に永続的な`idle`を作らず`idle` read modelを返す。
`start_working_trip_generation()`はcurrentなWorkingがある場合だけ開始し、既存の`generating`を上書きしない。
`store_working_trip_generation_candidate()`は最新の`generation_id`と開始時にcapturedしたWorking effective revision、
Working content digestが一致する場合だけ`candidate_ready`へ進める。`fail_working_trip_generation()`は最新identityの
`generating`だけを`failed`へ終端し、Working変更でdigestが不一致になった場合にも旧generationを再実行可能な終端へ移す。前者は`review` policyだけが利用し、
candidateは未信頼JSON objectとして1件だけ保持する。この段階ではAIG呼出し、formal Validation、adoption、FRMを
接続せず、既存`generation_requests`のqueue型AI Instruction/Patch経路も変更しない。後続Stepでauto adoptionまたは
review確定を接続する際も、`require_current_working_trip_generation()`で同じdigestを採用直前に再確認し、不一致なら
candidateをPhase 5境界へ渡さずConflictとする。Working編集を自動rebaseしない。

### 保持candidateのread-only preview（Phase 8）

FRMは`get_working_trip_generation_candidate_preview(trip_id, generation_id)`を呼び、
`{trip_id, generation_id, state: "candidate_ready", policy: "review", view}`を取得する。
`view`は保持candidateから既存`build_trip_detail_view()`で導出した旅程詳細モデルで、
Trip名・日付範囲・各dayのtitle / route_summaryと、順序、時刻、予定／移動、場所、候補場所、
status、コメント等の主要timeline情報を同じ形で表現する。Working overlayは重ねない。
候補previewの各entryは`direct_edit_paths={}`、`ai_local_update_target=null`とする。
weatherと一時candidate judgmentsは付加せず、既存モデルの空の既定値を使う。

最新generationが`review / candidate_ready`で、要求identity、Working content digest、
captured revisionが一致し、Workingがcurrentな場合だけ返す。保持candidateも既存の
formal Validation / constraint確認を通す。idle（generationなし）は`NotFoundError`、
状態・identity・policy・Working変更・staleの不一致は`ConflictError`、Working欠落は
既存gateの`NotFoundError`または`ConflictError`となり、いずれもpreviewを返さない。
不正candidateは既存Validationのエラーとし、failedへの遷移や修復は行わない。

previewは時点のread modelであり、raw candidate、request package、provider / AIG内部情報を
含まない。Trip / Working / candidate / generationを保存・変更せず、開始時reviewと
auto→review昇格で形状を変えない。FRMは「未反映の候補」として表示し、独自のcandidate解釈や
採用経路を持たない。preview成功はadoption成功・意図充足・保持保証ではなく、確定には
同じidentityで既存`adopt_working_trip_generation_candidate(trip_id, generation_id)`を使う。
確定時は改めて既存Validation / stale / Working gateとatomic adoptionを通る。

### 既存の生成結果接続

Step 4では`run_started_generation()`がcurrentな`generating`行から、開始時に固定した`generation_id`と
`request_package`をそのままprovider-neutral AIG requestへ組み立て、replaceable transportを1回だけ呼ぶ。
返却identityの不一致は最新stateを変更せずConflictとし、AIG safe failure、transport failure、malformed resultは
安全なfailure codeだけを`failed`へ保持する。candidate受領時は同じWorking-content digest gateを再確認してから、
手動candidateと共有するPhase 5 Schema / semantic / constraint Validationへ渡す。Validation失敗は
`invalid_candidate`、開始後のWorking変更は`obsolete_working`としてraw Validation/provider情報を残さず
`failed`へ終端する。旧generationのcandidateは拒否し、変更後Workingから新しいgenerationを手動開始できるが、
自動rebaseや自動retryは行わない。Step 4はcandidateを採用も永続保持もせず、`auto`の直結adoptionと
`review`の`candidate_ready`保持への分岐はStep 5に残す。

## 条件指定の新規予定追加（Issue #91）

[追加契約](conditioned-schedule.md)の意味境界から最大3候補を取得・明示選択し、
Direct Overrideで予定を1件追加する。通常詳細entryの`search_query`は元条件（既存項目はnull）。
正式場所は`places`、未決定候補は既存`candidates`で区別する。Frame画面への接続は後続。


## 実Tripレビューの意味境界（#138）

`time_mode: "none"`は設定なし、`undecided`は未定。いずれも時刻編集でstart / end /
durationMinutesをnullへ揃える。noneのview.time.labelは空文字、配置はorderを維持する。
具体的時刻は`time_mode: "fixed"`とstart / end / show_durationを渡し、CALがfixed / rangeを導出する。
直接追加も同じtime_modeを受け取る。省略時は既存の開始空欄→undecidedを維持する。

entry.important_comment_fieldsは`{source_id, comment}`配列。編集時は`important_comments`に
source_id→文字列のobjectを渡す。CALがその予定に紐づくBooking.notesへ保存する。
予約がない場合は予定自身をsource_idとして任意importantCommentへ保存する。
既存の予定固有コメントも保持する。空文字はnullへ変換する。別予定・別予約のIDは拒否し、
通常コメント等と同じtransactionで検証・保存する。共有Bookingを編集するとそのBookingを参照する表示にも反映される。
既存important_commentsは表示用文字列配列を維持する。

採用後のentry.placesにもtabelog_url / tabelog_ratingを返す。元Placeのurls / ratingをそのまま使い、
再取得・推測せず、候補一覧を隠しても通常表示で利用できる。
直接編集・追加とChat candidateのValidation失敗は項目pathと理由を返す。
JSON構文エラーには行・列を返す。失敗時の部分保存やcandidate自動修復はしない。
