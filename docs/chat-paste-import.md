# Chat貼付の新規Trip取込契約

Issue #89。[初期リリース仕様](initial-release.md)の貼付を、CALが一時解釈・確認・初回採用する。
FRM等の画面はこの意味境界を呼び、SQLiteやTrip JSONを直接変更しない。
この実装はCALのcommandと確認モデルまでで、FRMの画面・HTTP接続は含まない。
既存のread-only Web、Working手動往復、AI生成経路はそのまま保持する。

## 解釈と補正

`CalendarDomain.parse_chat_paste(text)`は書込みなしで次を返す。

- `draft`: `title`と`days`。日には`date / route_summary / items`があり、itemsは入力順。
- `unresolved`: 未解釈行の`line / text / reason`。不正な時刻・URL・座標や曖昧な移動補足もここへ返す。
- `requirements`: `path / message / required`。必須補正と、許容される未定値の通知を区別する。

予定draftは`kind="schedule" / title / category / place / candidates / time / status / comment`、
移動draftは`kind="transport" / from_place / to_place / mode / time / status / comment`。
地点は`name / address / location / urls`。`location`は`null`または`latitude / longitude`。
画面はdraftを編集し、未解釈行を修正した場合はその行へ`resolution="corrected"`、
利用者が明示的に除外した場合だけ`resolution="excluded"`を付ける。
未解釈行を非表示にしたり、確認なしで解決済みにしたりしない。
登録前の原文・draft・未解釈行は呼出側の一時編集sessionだけに置き、取消時に破棄する。

ラベルの全角／半角コロン、前後空白、空行、時刻・日付・座標の全角数字、
時刻の`～ / 〜 / -`、全角の項目区切り、通常のMarkdownコード囲みを吸収する。
名称やコメント全体はUnicode正規化せず、入力内容を保つ。
重複ラベルの上書きや不明な行の削除はしない。
カテゴリは直前の予定だけに属する。不正値・重複指定・予定外のカテゴリ行は未解釈に残し、
欠損時はcategory=nullの必須補正とする。移動・次の予定・次の日へカテゴリを引き継がない。
同名の場所・候補・移動端点にはそれぞれ別IDを割り当て、施設の同一性を推測しない。

## 現行Schemaへの対応

| 入力 | 対応・確認 |
| --- | --- |
| 旅行名・日付・予定内容 | 欠損を補正してから登録。年なし・無効日付も補正対象 |
| 日別代表エリア | `Day.routeSummary`。未定はnull。内部の必須`Day.title`は日付文字列を使い、代表エリアを複製しない |
| 開始～終了、開始のみ | `time.mode=fixed`、明示時刻だけを保存。終了・所要時間を推測しない |
| 未定時刻 | `undecided`、start/end/durationMinutesはnull |
| 日跨ぎ・時差が必要な時刻 | 推測せず補正対象。終了が開始より早い値は登録しない |
| 予定カテゴリ | Chatが予定ごとに`カテゴリ`ラベルで`観光`・`食事`・`宿泊`のいずれか1つを出力し、CALは`sightseeing / food / accommodation`へ対応付けてValidationする。予定内容・場所から推測せず、有効な貼付値はそのまま使い、不正・欠損時だけカテゴリの補正確認へ返す |
| 予定・移動の状態 | 初期値は`undecided`として確認に出す。時刻や場所の有無からconfirmed等を推測しない |
| 場所 | 名前がある場所をselectionへ設定。`未定`は架空のPlaceにしない |
| 候補 | candidatePlaceIdsだけに追加。訪問確定のselectionへ入れない。選択数はnull |
| 場所と候補が両方ない予定 | 現行Schemaの候補1件以上を満たさないため補正対象 |
| 住所・座標・URL | 直前の場所／候補に付ける。地点カテゴリは未分類の`other`、rating等はnull。https以外のURLや不正座標は未解釈へ返す |
| 名前のない地点の補足情報 | 名前を補正してから登録し、補足だけを捨てない |
| 予定のコメント | `ScheduleItem.summary`。複数行は改行で連結。候補の後でも予定のコメント |
| 移動の通常コメント | 現行Transportに保存先がないため必須補正。Booking／重要コメントに転用しない |
| 移動の補足地点情報 | 端点への帰属を推測せず未解釈へ返す。補正draftではfrom_place / to_placeを明示できる |

貼付外の準備・予約は空、Rio機能は未使用の`applicable=false / not_applicable`で初期化する。
Trip summary・補足・取得情報は生成しない。Schemaは変更しない。

## 確認と採用

`review_chat_paste(command_id, review)`は補正後の同じenvelopeを受け取り、
必須補正や未解決行が残れば`ready=false / requirements / unresolved / view=null`を返す。
補正済みならCALが完全Tripを構築し、既存のSchema / semantic Validationを通して
`ready=true`と既存のTrip詳細表示形状の`view`を返す。正式な編集・AI targetは無効化する。
不正な補正payloadや不正な完全Tripは`ValidationError`で拒否する。
渡された古い`requirements`を信用せず再計算し、未知fieldも黙って捨てず拒否する。

`import_chat_paste(command_id, review, confirmed=True)`は同じ検査を再実行し、
新規Tripだけをowner visibility / version 1で登録する。
返却は`{trip_id, status: "adopted", visibility: "owner", version: 1}`。
確認前の呼出し、必須補正や未解決行が残る入力は拒否する。
画面は確認した同じdraftを渡す。変更後は再表示・確認する。

`command_id`は呼出側が取込操作ごとに発行する一意な文字列で、再送では変えない。
CALはそこからTripと内部参照のIDを構築する。同じ操作のpreviewと採用でIDが一致し、
登録後の再送はConflictとなる。異なる操作IDなら同名旅行でも別の新規Tripになる。
previewは書込みをしない。

採用はValidation済みの完全JSONを同一ディレクトリの一時ファイルへ書き、
SQLiteの書込みtransaction内でcreate-if-absentによって正式ファイルを作成・登録する。
登録済みIDと未登録の既存ファイルはともにConflictとし、replaceしない。
通常の書込み／DB失敗は新規ファイルとDB transactionを撤回する。
プロセスの強制終了や電源断でDB commit前に完全JSONだけが残る場合は、
再送をConflictで止める。自動回復・既存ファイル削除は行わず、個別確認へ返す。
新たな恒久履歴・原文保存・recovery stateは作らない。

## 最小Validation

`sh Tests/chat-paste.test.sh`。正本の複数日例を読み、カテゴリを含む原文のままの一括登録、
カテゴリ3値・不正／欠損・未定値・表記揺れ・未解釈行・移動補足・Schema/semantic拒否、既存Trip不変、
同じcommandの再送、未登録ファイルの保護、DB失敗時の撤回を合成データで確認する。
FRM画面からの操作・実機確認・実データへの取込は別途接続後の確認対象。
