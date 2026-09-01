# Calendar Trip JSON仕様

> **Status:** Issue #46以降もformal Trip JSON、stable ID、cross-reference validationは維持する。Issue #54以降、既存Trip更新時のAI出力はJSON Patchであり、CALがcomplete candidateを構築する。この文書の旧complete再生成記述は新規Trip作成または履歴説明に限る。

## 1. 目的と基本方針

Calendar は旅行計画の完全 JSON を直接編集するエディターではない。採用済みbaseとactive Direct Overridesから得るeffective Tripを人が確認しやすい形で表示し、具体値の直接編集と自然言語のAI指示を別経路で受け付ける。

Calendar は旅行計画の閲覧を主目的とする。AI指示は補助機能であり、通常閲覧時に前面へ出さない。旅程詳細では対象予定を選択して編集画面を開き、具体値は意味ベースcommandとDirect Overrideへ、曖昧な変更意図は対象に紐づくAI指示へ分ける。

更新は次の流れで行う。

1. Calendar が採用済みの完全 JSON を読み取り専用で表示する。
2. ユーザーの具体値入力はCALの意味ベースcommandとしてValidationし、Direct Overrideへ反映する。
3. 候補判断やAI指示等の一時入力は、採用済み JSON と混同しない状態として保持する。
4. AI指示を使う既存Trip更新では、AIが採用済みbaseと更新材料を解釈してJSON Patchを生成し、CALが次版の完全candidateを構築する。
5. CALがcomplete candidateをValidationし、atomic adoptionに成功した場合だけ採用済みbaseを置き換える。

差分パッチや部分 JSON を正本にはしない。候補選択も確定変更ではなく、AI への指示である。内部実装で更新材料を `ChangeSet` 等と呼ぶことはできるが、ChangeSet 自体を画面には表示しない。画面のメモ欄には、内部データや機械向け差分ではなく、AI に伝える指示だけを表示する。

## 2. データ全体像

すべての主要オブジェクトは安定 ID を持つ。ID は表示順、名称、時刻、候補の確定、旅行後の記録追加によって変更しない。参照は表示名ではなく ID で結ぶ。

### Trip

旅行計画のルートオブジェクト。

- `id`: 安定 ID
- `title`: 旅行名
- `dateRange`: 旅行の開始日と終了日
- `days`: `Day` の配列
- `places`: 旅行内で共通利用する `Place` の配列
- `transports`: `Transport` の配列
- `preparation`: `Preparation`
- `rioPlan`: `RioPlan`
- `bookings`: `Booking` の配列

### Day

旅行中の1日を表す。

- `id`: 安定 ID
- `date`: 対象日
- `title`: その日の見出し
- `routeSummary`: その日の主な経路を短く表示する任意項目
- `scheduleItems`: `ScheduleItem` の配列
- `transportIds`: その日に表示する `Transport` への参照

Day 内の表示順は配列位置だけに依存せず、各表示対象が持つ明示的な `order` で管理する。同じ Day に ScheduleItem と Transport を時系列表示する場合も `order` を使う。`order` は時刻とは独立しており、時刻未定の項目も配置できる。

### ScheduleItem

旅程上の予定を表す。移動そのものは含めず、Transport と分離する。

- `id`: 安定 ID
- `dayId`: 所属する Day の ID
- `order`: Day 内の表示順
- `action`: 何をするかという「行動」
- `summary`: 予定の補足を短く表示する任意項目
- `time`: `TimeSpec`
- `placeSelection`: `PlaceSelection`

「行動・時間・場所」は独立したフィールドとして保持する。たとえば「12:00に候補Aで昼食」を一つの文字列にまとめない。これにより、行動を維持したまま時刻だけを変更する、または場所候補だけを比較する操作を可能にする。

### TimeSpec

時間の確定状態と値を表す。

- `mode`: `fixed` / `range` / `undecided`
- `start`: 開始時刻。`fixed` と `range` で使用する
- `end`: 終了時刻。時間レンジを明示するときに使用する
- `durationMinutes`: 所要時間。開始・終了の片方だけが分かる場合や目安時間にも使用できる

`fixed` は特定時刻を基準とする予定、`range` は開始可能範囲または時間帯を持つ予定、`undecided` は時刻未定の予定を表す。`range` の具体的な意味が開始可能範囲か滞在時間帯かは、フィールド名または補助属性で曖昧さがないデータ契約にする。実装時に JSON Schema と合成サンプルで確定する。

### PlaceSelection

ScheduleItem と場所候補の関係を表す。

- `candidatePlaceIds`: 1件以上の `Place` ID。候補が1件の場合も同じ構造を使う
- `selection`: 現時点で選択された候補 ID の配列
- `minSelections`: 選択する最小件数。未定の場合は `null`
- `maxSelections`: 選択する最大件数。上限未定の場合は `null`

単一候補、複数候補、複数候補から複数件を選ぶ場合、および選択数自体が未定の場合を扱う。選択数は次のように表現する。

- 1箇所: `minSelections: 1`, `maxSelections: 1`
- 1～2箇所: `minSelections: 1`, `maxSelections: 2`
- 何箇所か未定: `minSelections: 1`, `maxSelections: null`
- 完全未定: `minSelections: null`, `maxSelections: null`

画面上の候補選択は、選択結果そのものを確定する操作ではなく、**「この候補を選ぶ」という AI への指示**である。一時状態として保持し、元 JSON の `selection` を直接変更しない。AI がその指示を解釈して次版 JSON を生成し、ユーザーが承認して初めて確定する。

### Transport

地点間の移動を表す独立オブジェクト。ScheduleItem の一種として扱わない。

- `id`: 安定 ID
- `dayId`: 所属する Day の ID
- `order`: Day 内の表示順
- `mode`: 徒歩、鉄道、バス、車、航空等の移動手段
- `fromPlaceId`: 出発地点の Place ID
- `toPlaceId`: 到着地点の Place ID
- `time`: `TimeSpec`
- `bookingId`: 予約情報がある場合の Booking ID

### Place

ScheduleItem、Transport、Booking、将来の TripRecord から共通参照する場所マスター。

- `id`: 安定 ID
- `name`: 表示名
- `summary`: 候補名の横に短く表示する任意の補足コメント
- `category`: restaurant / hotel / station / attraction / other 等
- `address`: 住所
- `location`: 緯度・経度
- `urls`: 公式サイトや参照先
- `rating`: 外部評価。評価値、固定された評価元、参照時点を持つ

同じ場所を予定ごとに複製せず、共通 Place を ID 参照する。評価元は場所カテゴリごとに固定し、**レストランは食べログ、ホテルは楽天トラベルだけを使用する**。レストランやホテルについて他の評価元へ切り替えたり、複数サイトの評価を混在・合成したりしない。評価には値だけでなく固定評価元と参照時点を保持し、食べログと楽天トラベルの異なる尺度を一つの共通点数として混同しない。

## 3. 旅行支援データ

### Preparation

Preparation は妻の旅行準備を管理する。

- `id`: 安定 ID
- `tasks`: 準備作業の配列
- 各作業は安定 ID、内容、作業ごとの期限、完了状態、表示順を持つ

Preparation は個別の持ち物を大量に列挙するのではなく、「荷造り」「日時指定券の確認」等の作業単位で扱う。分類見出しや準備全体で一つだけの期限には依存せず、各作業が `dueDate` を持つ。完了した作業も非表示または削除せず、取消線を使わずに完了状態が分かる形で表示し続ける。画面上のチェックは一時状態として AI への指示に変換し、採用済み JSON を直接書き換えない。

### RioPlan

RioPlan は Preparation とは独立し、Rio の同行・預け先と持参品を管理する。

- `id`: 安定 ID
- `careMode`: `accompany`（同伴）/ `leave`（預ける）/ `undecided`（未定）
- `careDecisionDueDate`: 同伴か預けるかを早期決定するための期限
- `careDetails`: 預け先等の補足
- `packingTemplate`: 標準持参品テンプレート
- `packingItems`: 今回の持参品

同伴か預けるかは旅行準備の早い段階で決定する必要がある。`careMode` が `undecided` の間は決定期限と未決定状態を目立つ形で表示する。標準持参品テンプレートから旅行ごとの項目を作れる。今回不要な項目は削除せず、`notNeeded` 等の状態で不要と明示し、必要・未完了の項目より下段にまとめて表示する。完了状態と不要状態は区別する。

### Booking

Booking は予約と費用を管理する。

- `id`: 安定 ID
- `category`: `accommodation`（宿泊費）/ `transport`（交通費）/ `activity`（観光・チケット）/ `other`（その他）
- `status`: 未予約、予約済み、変更・取消等を表す状態
- `targetDate`: 予約・手配の対象日を表す必須の日付。予約済みかどうかは `status` を正本とし、別の真偽値には重複保持しない
- `placeId` または `transportId`: 対象への参照
- `amount`: 金額
- `currency`: 通貨
- `notes`: 予約番号、条件、連絡事項等の予約に関する備考

費用は宿泊費、交通費、観光・チケット、その他のカテゴリ別に集計でき、旅行全体の合計も算出できる。飲食を独立した Booking 費用カテゴリにはしない。集計値は個々の Booking を根拠に導出し、二重に正本を持たない。

`notes` は予約番号、条件、連絡事項等の正式な予約情報・備考として採用済み JSON に保持する。一方、「このホテルをキャンセルして別候補を探して」等の AI への指示は Booking の正式 JSON に含めない。Calendar 内部の一時状態として保持し、AI がその指示を反映した次の完全 JSON を生成した時点で消える。

## 4. 画面と更新境界

Calendar は次を担う。

- 採用済み完全 JSON の表示
- 旅程、地図、準備、RioPlan、予約・費用、メモの閲覧
- チェック、場所候補選択、AI への指示メモの入力。候補選択も「この候補を選ぶ」という AI への指示として収集する
- 未送信・確認待ち等、一時状態であることの明示

Calendar は次を担わない。

- 採用済み完全 JSON のフィールドを画面操作で直接更新すること
- 候補選択をその場で確定済みデータにすること
- 内部 ChangeSet の構造や差分を利用者向け画面に表示すること
- AI が再生成した次版をユーザー確認なしで採用すること

旅程詳細の確定UI要求は [`trip-detail-ui.md`](trip-detail-ui.md) を正本とする。通常閲覧中に対象ごとのAI指示入力欄を常設せず、選択した予定の編集画面内で対象を確認して任意のAI指示を入力する。ほかの画面の指示入口は、その画面の実装Phaseで必要な範囲だけ確定する。主要画面へのナビゲーションは画面下部に固定し、本文を隠さない余白を確保する。

旅行詳細は `カレンダー / 旅程 / 地図 / 準備 / コメント` の5画面を固定フッターで移動する。トップのカレンダー画面には固定フッターを置かない。未処理の指示をコメント画面でどう表すかと、予定編集画面内のAI指示との役割分担は後続Phaseで確定する。

旅行ヘッダーの期間は開始側だけに年を付けた `yyyy/m/d〜m/d`、画面内の日付は `m/d`、時刻は先頭ゼロなしで表示する。Calendar 全体は緑を基調とする。旅程詳細の日付には日別の識別色を付けず、同色で表示する。

旅程は全日程をcompact timelineとして縦に初期表示する。日単位では折りたたまない。上部に日付とカテゴリーのfilterを同じ1行で置き、強いpill形状を使わない。個別予定は `時刻 / カテゴリー / 本文` の対応を保ち、詳細は [`trip-detail-ui.md`](trip-detail-ui.md) に従う。

地図の日付操作もfilterとし、表示中の日に属する地点・ルート・地点一覧だけを表示する。地図本体は共通ヘッダーとfilterの下にsticky表示する。地図側の日別折りたたみ、地点番号、カテゴリーfilterの詳細はGoal 2で見直し、旅程詳細の確定UIから機械的に転用しない。

準備画面は `準備すること / リオ / 予約・手配` の3セクションで構成する。iPad mini 相当幅では準備することとリオを上段の2カラム、予約・手配を下段全幅に配置する。準備はチェック・日付・項目、予約はチェック・対象日・種類・内容・金額を基本列とし、各予約行の金額を表示する一方、ページ下部に費用合計ブロックは置かない。リオ対象外の旅行ではリオセクションを表示せず、対象旅行では同行または預ける状態と単純な持参品チェック一覧を表示する。

一時状態は画面を閉じる、AI に渡す、次版を却下する等のライフサイクルを定義し、採用済み JSON と混同しない。永続化方式はアプリケーション基盤の決定時に別途確定する。

AI への指示メモは Trip、Day、ScheduleItem、Transport、Booking 等の正式 JSON フィールドには含めない。画面では対象オブジェクトと関連付けて表示できるが、Calendar 内部の一時状態として保持し、AI が指示を反映した次の完全 JSON を生成した時点で消える。Booking の `notes` は正式な予約情報・備考であり、この一時的な指示メモとは異なる。

## 5. 将来拡張: TripRecord と旅の記録

将来 `TripRecord` を追加し、旅行後の実績を計画と分離して記録する。

- 実際に訪問した Place
- 予定外に訪問した Place
- 実際の開始・終了時刻、所要時間
- 実際に利用した Transport
- 旅行後のコメントや出来事
- 計画上の Trip、Day、ScheduleItem、Transport、Place への ID 参照

予定と実績を上書きで混ぜず、比較可能な別オブジェクトとして保持する。予定外訪問にも新しい安定 ID を付け、必要に応じて共通 Place を追加・参照する。

さらに、写真の撮影日時、位置情報等のメタデータを TripRecord、Day、ScheduleItem、Place と関連付けられる設計にする。将来 AI が写真群から代表写真を選び、時系列・場所・実績を使って「旅の記録」を生成できるようにする。この関連付けを長期に維持するため、各オブジェクトの安定 ID は JSON の再生成後も可能な限り継承し、同一対象に安易に新 ID を振らない。

## 6. 未確定事項と実装時の契約化

正式な機械可読契約は `Schemas/trip.schema.json` とする。ChatGPT は同スキーマと `docs/trip-json-generation.md` に従って完全 JSON を生成し、`scripts/validate_trip.py` の構造検証と参照整合性検証を通過したJSONだけをCalendarへ渡す。Calendarは旧形式の変換や不足値の自動補正を行わない。

時刻は `HH:MM`、日付は `YYYY-MM-DD` とする。`TimeSpec.mode` は次の契約で使う。

- `fixed`: `start`を必須とし、終了が分かる場合だけ`end`を指定する
- `range`: `start`と`end`を必須とし、その時間帯を表示する
- `undecided`: `start`と`end`を`null`にする

同じ説明を複数フィールドへ繰り返さない。`Day.title`は日付ではなくその日のテーマ、`routeSummary`は経路、`ScheduleItem.action`は行動、`summary`は短い補足、`details`は追加で必要な事実だけを保持する。Place名や時刻を`action`へ埋め込まない。

次の詳細は引き続き別Issueで確定する。

- 一時状態の保存期間と破棄条件
- 外部評価の取得・更新方法
- TripRecord と写真メタデータの詳細構造

実データや私的データを仕様例に使用しない。リポジトリへ置く例は合成・非機密データに限定する。
