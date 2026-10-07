# Chatからの日程保存（Frame #177 Phase 3 Step 1・2）

既存Remote Desktop Commander（RDC）でMacのCAL専用CLIを呼ぶ。CALの既存SQLiteと正式Trip JSONが正本。Frameを開く／再読込することは保存条件ではない。旅程も本書の専用コマンドで正式保存する。通常予定・タスクの定期日程も扱う。保存後は[専用Google一方向連携](google-calendar.md)を使い、CAL receiptとGoogle反映結果を区別する。

## Chatで使う

ChatでRDCを選択し、対象Mac `usMac-miniM4Pro.local` を選ぶ。次の入口を最初に伝える（またはこの文書を読ませる）。

> 日程・タスクの操作は既存機能の範囲でRDCから `/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py` を使ってください。変更前に対象IDと最新revisionを取得し、要求IDと送信内容をチャットに残してください。応答不明時は同じ要求IDを照合し、別IDで追加し直さないでください。CALのcommitted receiptを受け取ってから保存済みと報告してください。未対応の依頼は未対応と伝えて追加案を提示し、登録依頼だけを根拠に機能開発へ進まないでください。

その後は「10月8日9時に打合せを追加」「このタスクを完了」「開始を10時へ変更」等を依頼する。対象が曖昧ならread結果から特定してから操作する。候補の複数一致を勝手に1件へ絞らない。ChatはCALへ直接SQLを書いたり、別の即席更新スクリプトを作ったりしない。既存RDCの汎用実行権限は残る。専用CLIを使うことは運用規約でありRDCの技術的な権限制限ではない。

### 通常操作と機能開発の境界

通常の日程・タスク・旅程の登録／変更は、現行の専用CLIが提供する機能内で行う。既存機能で実行でき、対象と内容が明確な依頼には、毎回の追加確認を要求しない。

未対応の条件・操作なら、未対応であることと必要な機能追加案をusへ提示する。既存機能で可能な代案があれば、依頼との差分も示し、意図を変えた登録を勝手に行わない。日程登録依頼だけを根拠にコード変更・開発Issue／PR作成・merge・本番反映へ進まない。機能追加への明示指示がある場合に、現行TDSの通常開発手順で進める。RDCの汎用実行権限は機能開発の許可を意味しない。

### 読み取り・照合

```sh
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py doctor
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py read --start 2026-10-01 --end 2026-10-31
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py get --kind todo --id '取得済みの対象ID'
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py lookup --request-id '送信時の要求ID'
```

`read`は両端を含む期間の通常予定・日付付きタスク（完了を含む）を返す。`get`は対象の全保存値とrevisionを返す。日付なしの既存Todoは期間readの対象外だがIDによるgetは可能。`doctor`のreadyは接続・receipt表・定期日程表の準備確認であり、保存成功ではない。日時は既存CALと同じローカル日付と24時間表記（通常運用Asia/Tokyo）。日付ISO `yyyy-mm-dd`、時刻`HH:mm`、任意値の解除はnull。

### 正式更新

要求IDは操作ごとに新しいUUID等を生成する（1〜128文字、英数字・`.`・`_`・`:`・`-`）。送信前に要求IDと変更内容を会話へ残す。一度送信したIDと内容を、結果不明だからと作り直さない。

CLI `apply`の標準入力へJSONを渡す。シェルの変数展開を防ぐ引用付きhere-documentを使い、JSONは正しくシリアライズする。JSON内の改行は`\n`として渡す。UTF-8 JSONをbase64化した`--request-base64`も利用可能。

以下は形式例。依頼のない実行や検証目的の実データ作成には使わない。

```sh
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py apply <<'CAL_SCHEDULE_REQUEST'
{"request_id":"example-replace-with-new-uuid","kind":"event","action":"save","values":{"title":"打合せ","start_date":"2026-10-08","start_time":"09:00","notes":null}}
CAL_SCHEDULE_REQUEST
```

| 操作 | kind / action / values |
| --- | --- |
| 予定追加 | event / save / title, start_date, 任意start_time・end_date・end_time・notes |
| タスク追加 | todo / save / label, due_date, 任意due_time・notes |
| 変更 | eventまたはtodo / save / 変更するfieldのみ。省略fieldは保持 |
| 削除 | eventまたはtodo / delete / `{}` |
| 完了・未完了 | todo / complete / `{"completed":true}` またはfalse |

追加以外では、同じJSONに`id`と`expected_revision`を必ず付ける。両方とも直前のread/get結果を使う。件名や日付をIDの代わりにしない。既存共通処理により空の件名・不正日時・終了が開始より前・未対応field等を拒否する。旅程は後述の専用形式で更新する。

```json
{"request_id":"example-replace-with-new-uuid","kind":"todo","action":"complete","id":"取得済みID","expected_revision":"sha256:取得した値","values":{"completed":true}}
```

### 保存確定の判定と応答不明

- exit 0と`status=committed`、かつreceiptの要求ID・対象・操作・内容が一致して初めて保存確定。`receipt_id`、`entity_id`、`revision`（単発削除後はnull、定期は更新後のシリーズrevision）、`committed_at`を結果として会話へ残す。単発の削除receiptは削除前の内容とprevious_revisionを保持する。
- 例：「CAL保存済み。対象ID …、要求ID …、receipt …、revision …」。保存内容も短く示す。RDCの「Process started」やFrame画面の表示だけで成功扱いにしない。
- RDCがPIDを返したらread_process_outputで終了・出力を取得する。通信断・出力なし・timeout・`status=unknown`は結果不明。`lookup --request-id`で照合する。
- lookupがcommittedなら元の確定receipt。`not_found`（exit 4）は現時点で確定receiptが見つからないだけで、未実行の証明ではない。同じ要求ID・同じ内容で再送できる。別IDで再作成しない。
- 同一ID・同一内容の再送は`resolution=replayed`で元receiptを返し、二重更新しない。削除後や後続変更後でも元の操作結果を返す。**receiptはその操作時点の結果**であり、現在値が必要ならgetで読み直す。
- 同一ID・異なる内容は`request_id_payload_conflict`（exit 3）で拒否。revision不一致は`revision_conflict`（exit 3）。最新内容を取得し、依頼と照らして内容を再確認した別操作には新しい要求IDを使う。staleを無条件上書きしない。
- 入力拒否はexit 2。ストレージ利用不能等はexit 5/result unknown。保存できたと推測せず照合する。拒否された操作のreceiptは作らない。

### 完了報告の確認範囲

保存と利用画面への反映は、次の確認範囲を区別して報告する。

| 確認 | 分かること |
| --- | --- |
| 保存確定receipt | その要求のCAL正式保存が確定したこと |
| CLI再取得 | CAL専用CLIが返す現在の保存値・各回 |
| Frame API | 既存Frameプロセスが返す表示用データ |
| 公開画面 | 公開URLで取得した画面・表示。HTTP応答だけならHTTP確認と明記 |
| Safari等の実機 | その端末で実際に確認した表示・操作 |

実施した範囲と未確認の範囲を示す。receiptやCLI再取得の成功だけで「Frame表示済み」「実機確認済み」と報告しない。API成功も公開画面・実機表示の確認を代替しない。保存済みなのに表示されない場合は、まず保存結果とFrame APIの違いを確認し、別要求IDで再登録しない。CALコード更新を既存Frameへ反映する手順は[運用入口](operation.md#calコード変更のframe反映)を参照する。

## 所有・transaction・revision

`apply_schedule_request`はBEGIN IMMEDIATEの同じ接続内で、要求ID照合→現在行のrevision確認→既存`_change_schedule`→receipt保存を実施し、commit後にだけ成功を返す。Frameの`change_schedule`も同じ更新・Validation本体を使う。試作subclassや故障注入は本番へ持ち込まない。

revisionは正本行全値（更新日時を含む）のSHA-256。連番ではなく内容fingerprintで、Frameや既存CRUDによる内容変更も検出する。読み取り後に値が変わって元の値・日時まで完全に戻った履歴の検出を保証するものではない。同時再送はSQLiteの書込みlockとrequest_id主キーで直列化する。

receiptは既存CAL DBの`schedule_receipts`に保持し、自動削除しない。元データとreceiptは同じbackup対象。別サービス・別DB・公開HTTP更新入口は追加しない。Googleの未反映・再試行・認証は[所有契約](google-calendar.md)へ集約する。CLIのreadは旅程loadを呼ばず、context/candidateに触れない。

## 配置・初回反映

標準接続先は既存Frameと同じ`/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3`。データrootも既存Calendar_Local。起動時にDBを作ったりmigrationしたりしない。`--database`と`--local-root`は合成テストの隔離用で、通常Chatでは指定しない。

既存DBへはSQLite backupを取ったうえで次の明示migrationを1回実行し、既存各tableの内容保持を確認する。再実行は変更なし。新規initializerにもreceipt表を含める。schema version 3を維持し、nullable列追加や既存行の変更はしない。

```sh
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/migrate_schedule_receipts.py /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3
```

通常のChatからmigrationやinitを実行しない。導入後はdoctorでreadyを確認する。切戻し時はCLI利用を止め、receipt表を削除せず保持する。追加の常駐・RDC設定変更・認証変更は不要。

## 旅程の正式更新（#205）

同じCLI・同じlookup・同じCAL SQLite receipt表を使う。予定/Todoと旅程のJSON形式は別で、全旅程削除は提供しない。

- `trips`：登録済み旅程の一覧。対象IDを特定する。
- `trip-get --id <Trip ID>`：effective complete Trip、未処理instructions、revisionを取得する。Direct Overrideと固定自宅を含む。revisionはtrip_version/effective_hash/instructions_hashの組で、指示の追加・変更も競合判定に含める。
- `trip-plan`：標準入力の `{"trip":<complete Trip>,"existing_trip_id":<更新対象ID>}` から既存の地図補完planを取得する。新規時はexisting_trip_idを省略する。検索内容の確認用で、保存はしない。
- `trip-resolve`：`trip-plan`と同じ入力から不足地点を既存FrameのGoogle Maps接続で1回ずつ検索し、`coordinate_results`とattempted / filled / missing / existing件数を返す。Frame画面を開く必要はないが、既存loopback Frameサービスと地図接続設定が利用できる必要がある。Secretは出力しない。
- `apply`：下記の旅程要求を標準入力（またはrequest-base64）で渡す。

```json
{
  "request_id": "example-replace-with-new-uuid",
  "kind": "trip",
  "action": "save",
  "expected_revision": {"trip_version": 1, "effective_hash": "取得値", "instructions_hash": "取得値"},
  "handled_instruction_ids": [],
  "coordinate_results": {},
  "trip": {}
}
```

これは形状例であり空tripは無効。新規登録はaction=create、expected_revision省略、handled_instruction_idsは空。更新はaction=saveと最新trip-getのrevisionを指定する。getのtripを出発点に意図した変更だけを適用し、既存ID・予約・選択済み地点・変更対象外の値を保持する。対応した指示IDだけを列挙する。新規createは既存ID・未登録の同名正式ファイルを上書きしない。

座標補完は既存CALのplan/result契約を再利用する。既存座標・手動補正・固定自宅設定を保持し、同一点をまとめて補完する。通常Chatは保存前に`trip-resolve`を実行し、その`coordinate_results`をそのまま`apply`へ渡す。検索対象ごとに結果キーが必要で、検索自体を省略した空`{}`や一部欠落は`coordinate_results_incomplete`で拒否する。検索を実行して結果がなかった地点は値nullとして明示し、その地点だけ未取得のまま保存できる。receiptのcoordinates（filled/missing/existing）と未取得の有無を報告する。必要な位置補正は既存Frame地図編集で行える。座標を推測して埋めない。

`trip-resolve`は既存Frameのloopback `map-config`からブラウザ用接続設定をメモリ内で取得し、Places Text Search (New)へ名称・住所／当日エリアの既存queryだけを送る。新しいcredential・常駐処理・providerは追加しない。接続設定自体をログ・receipt・Gitへ残さない。Frame接続または地図設定が利用できなければresolveを失敗として止め、未検索を空結果に読み替えて保存しない。

CALの共通Schema・semantic・Todo参照検証と、既存の`.adoption` staging/journal・SQLite transactionを使う。正式JSON置換前の中断は未採用へ、置換後はSQLiteのversion・指示・Overrideとreceiptを確定させて収束する。lookupは該当要求の未完journalを回復してからreceiptを返す。反映後の応答喪失でも元receiptを取得できる。復旧不能な不一致は確定済みと返さず、journalや正式ファイルを手編集しない。

旅程receiptは保存したcomplete Trip、revision、対応指示、座標補完件数も含む。正式JSON＋SQLite＋`.adoption`は従来どおり同じCAL LocalDataの管理対象で、別DBは作らない。receiptと保存データは非公開扱いでGit/Issueへ転記しない。

通常Chatのcontext/candidate授受、context自動共有、Frame load/reloadのcandidate自動採用は停止した。残存ファイルは削除しない。Frameの手動新規JSON取込、直接編集、Chat指示入力は維持する。旧Envelopeのdomain処理は保守・既存中断復旧用に保持するが、通常のChatから呼ばない。RDC利用には既存Macの稼働・接続が必要。iPhoneでの動作・実通信断の確認範囲はIssueの実測記録を参照する。

## 定期予定・タスク（#207 / Phase 3 Step 2）

条件の登録・変更はChatの専用CLIで行う。Frameに条件フォームは追加しない。旅行の定期化は対象外。通常項目の検証・時刻・メモの扱いは単発と共通。

- `series` はシリーズ一覧、`series --id <series_id>` は条件・期間別テンプレート・単回例外と最新revisionを返す。
- `read` は指定期間と重なる各回を通常項目形式で返す。`get --kind event|todo --id <回ID>` は各回の現在値を返す。
- 回IDは `rec:<series UUID>:<元の発生日>`。単回の日付移動後も同じIDで、`occurrence_date`が元の発生日。`series_id`も返す。
- シリーズと各回は `series:<UUID>:<連番>` のrevisionを共有する。別の回の変更でも連番が進むため、操作前に対象を再取得する。古いシリーズ／回の上書きは拒否する。

`apply` に `scope` を指定する。新規シリーズは `scope=series`、`action=save`、id・expected_revisionなし。以下は形式例（依頼なしに実行しない）。

```json
{"request_id":"example-replace-with-new-uuid","kind":"todo","action":"save","scope":"series","recurrence":{"frequency":"weekly","start":"2026-10-05","until":null,"weekdays":[1,3]},"values":{"label":"定期タスク","due_date":"2026-10-05","due_time":"09:00","notes":null}}
```

`recurrence.start` とテンプレートのstart_date／due_dateは一致させる。開始日・終了日は両端を含む。開始日そのものが条件に該当しなければ、最初に該当する日から発生する。

| frequency | 追加項目・動作 |
| --- | --- |
| daily | 毎日 |
| weekly | weekdays: 日曜0〜土曜6の重複しない配列、複数可 |
| monthly | month_day: 1〜31。存在しない月はスキップ |
| month_end | 各月の最終日。平年・閏年を反映 |
| yearly | `recurrence.start` の月日と同じ日に毎年。2/29など存在しない年はスキップ |

untilは省略／nullで無期限。休日移動はしない。各回の終了日はテンプレートの開始日からの日数差を維持し、時刻も維持する。無期限でも取得期間に必要な回だけ計算し、全回の事前保存や常駐生成はしない。

変更・削除・完了では回IDと最新expected_revisionを指定する。

| scope / action | 動作 |
| --- | --- |
| this / save | 今回だけ変更。valuesに変更fieldのみ。recurrence指定不可 |
| this / delete | 今回だけ削除。valuesは空 |
| this / complete | Todoの今回だけ完了／未完了。values.completedにboolean |
| following / save | 指定回を含む今回以降の条件／テンプレート変更 |
| following / delete | 指定回を含む今回以降を削除。valuesは空 |

followingの境界は表示日ではなく元の発生日。条件変更時はrecurrence全体を渡し、startは境界以降とする。条件省略なら現在の条件を引き継ぎ、startを境界日にする。テンプレートの日付は新しいstartへ移し、複数日の期間を保持する。valuesで日付を指定する場合も新しいstartと一致させる。

過去の回・例外・完了は維持する。明示済みの単回例外（変更・削除・完了）はfollowingの条件変更後も優先して保持し、消した回を再生成しない。following削除は境界以降の例外も含めて除外する。移動した回も元の発生日で判定する。対象や範囲が曖昧な依頼は、実行前にChatで特定する。

保存とreceiptは既存SQLiteの同一transactionで確定する。返すreceiptにはseries_id、scope、対象回のentity_id／occurrence_date、更新後revision、保存内容（itemまたはseries）を含む。新規seriesのentity_idはシリーズID。削除はdeleted=true。要求ID照合・同一内容再送・異なる内容の拒否・応答不明時のlookupは単発と同じ。Frameの既存編集・削除・完了は常にthisとして共通処理へ渡す。

既存DBはbackup後に `scripts/migrate_recurrence.py <既存DBパス>` を明示実行する。schedule_series（id、kind、revision、data_json）だけを追加し、既存行・schema version 3は維持する。data_jsonは開始日で区切った条件／通常項目テンプレートと元の発生日で索引した単回例外。receipt表は共用し、自動削除しない。通常起動・Chat操作ではmigrationしない。追加サービス・RDC設定変更・別DBは不要。

## 旅行先行管理とGmail起点登録（#221）

`travels` / `travel-get --id <ID>`で全旅行・基本情報・関連項目を取得する。旅程の有無はhas_itinerary、遷移IDはitinerary_id。旅行の先行作成と更新はapplyのkind=travel、action=save、valuesを使う（更新にはid / expected_revision）。要求ID・receipt・lookupは既存契約と共通。基本情報fieldは[日程契約](schedule.md#独立した旅行管理221)を正本とする。

旅程作成前にtravelsを確認し、該当する旅行があればそのIDをcomplete Trip.idに使ってkind=trip / action=createで接続する。該当がなければ旅行管理も同時作成される。複数一致は勝手に選ばない。旅行の基本情報はCALへ保存し、表示期間と旅程内行動日付の変更を区別する。

予約（交通・宿泊・食事・ツアー等）と旅行タスクは通常Event/Todoとして保存し、旅行へtrip_idで関連付ける。単なる現地行動を通常日程へ複製しない。関連付け/解除はこの専用CLIのsaveで行う。

Chat/Gmail登録では、明確な新幹線はshinkansen、その他の鉄道はrail、飛行機はairをcategoryに選ぶ。CALは自然言語から分類を推測しない。Gmail登録前に元メール参照を取得し、categoryを内容から選ぶ。Google側に同じ予定があるか既存Google接続で確認し、件名だけでは同一と判断せず、対象予約・日付時刻・メール根拠を照合する。同一ならそのcalendar ID / event IDを取得してgoogle_calendar_id / google_event_idの組を指定する。Macのapp.created scopeからprimaryを探索する機能や権限拡張は追加しない。照合できなければ未確認と伝え、重複回避済みと報告しない。

CAL正式保存→旅行関連付け→Google反映の順。旅行が既知なら同じ正式保存にtrip_idを含め、保存commit後のGoogle送信を使う。後から関連付ける場合は最新revisionで追加saveする。CAL receipt、外部予定参照、Google送信結果を区別する。既存スケジュールタスクの指示文変更はこの機能導入とは別に扱う。
