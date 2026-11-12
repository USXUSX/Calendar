# Chatからの日程保存（Frame #177 Phase 3 Step 1・2）

CALのChat更新は接続済みMacの標準実行経路（`exec_command`、継続は同じsessionへの`write_stdin`）を優先して、既存のCAL専用CLIを呼ぶ。利用できない場合は既存Remote Desktop Commander（RDC）へ戻せる。CALの既存SQLiteと正式Trip JSONが正本。Frameを開く／再読込することは保存条件ではない。旅程も本書の専用コマンドで正式保存する。通常予定・タスクの定期日程も扱う。保存後は[専用Google一方向連携](google-calendar.md)を使い、CAL receiptとGoogle反映結果を区別する。

## 通常操作の短い入口

新規チャットではこの節から始め、下表の該当節だけを追加で読む。取得ツールが行範囲を指定できるなら、まずこの入口の範囲だけを取得する。既存機能による日程・旅程の更新を、開発・障害調査として始めない。適用済みの上位指示は守るが、通常操作だけを理由にTDS・Issue履歴・ソース・Schemaを探索し直さない。新規・全体Trip生成には生成ガイドを使う。

1. 計測する依頼では、**最初のツール呼出し内で、手順取得・接続先探索より先に呼出元の時刻を記録**する。[計測境界](#新規チャットでの短縮確認285)に従い、計測準備後へ開始点を移さない。
2. 対象Macは `usMac-miniM4Pro.local`。そのMacへの標準実行経路が利用できれば使い、Cloudのshellしか使えない場合などは既存RDCでそのMacを選ぶ。Cloud shellでMacのCLIを探さない。RDCのdevice IDが未解決なら一覧から選び、複数端末を推測しない。
3. [一括の読取り確認](#接続確認を一度に行う285)を行い、対象Mac・作業場所・Python・CLIを確認する。確認済みの同じ接続・パスを通常操作の途中で繰り返し調べない。
4. 下表で操作を選ぶ。Trip IDが不明なら `trips`、判明したら最新の `trip-get` で対象項目・revision・未処理指示を確認する。局所更新で対象項目IDも既知なら `trip-get --id <Trip ID> --item-id <項目ID>` で必要な情報だけを取得する。既知IDでも保存値・revisionは使い回さない。対象の複数一致は確認する。
5. 要求IDと送信内容を短く会話へ残し、専用CLIで保存する。最終exit 0と `status=committed`、receiptの要求ID・対象・操作・内容の一致を確認する。保存確定結果を回収したら計測を止め、**保存完了を先に報告**する。
6. 続けてlookup・再取得・必要なFrame反映を照合する。これは後続確認として報告し、保存確定までの時間へ加えない。応答不明時は同じ要求IDをlookupし、同内容だけを再送する。

| 依頼 | 読む節・使う操作 |
| --- | --- |
| 通常予定・Todoの追加／変更／完了 | [正式更新](#正式更新)：read/get → apply |
| 既存Tripの名称・時刻・コメント等の対応済み局所変更 | [局所変更](#旅程の局所変更)：trip-get（対象ID既知なら--item-id）→ trip-operation。complete Tripの再生成・trip-resolveは不要 |
| 既存Tripの大きな組み直し・局所操作にない変更 | [全体保存](#旅程の正式更新205)と[生成ガイド](trip-json-generation.md)：最新trip-getを基にcomplete Tripをsave |
| 新規Tripの生成・登録 | [全体保存](#旅程の正式更新205)と[生成ガイド](trip-json-generation.md)：travels確認 → complete Trip生成 → resolve → create |
| 鉄道経路・地点変更、定期予定、旅行管理 | 本書の該当節とそこから参照する所有契約だけを読む |

新しい地点・候補の追加や場所の差替えは、名称文字列だけの編集とは分ける。局所変更で扱えるかと地点取得・座標の契約を確認し、全体保存を使う場合は従来のtrip-resolveを省略しない。対応項目・未処理指示の消込みなどが局所操作で表せなければ全体保存へ進む。

新規チャットで入口を指定する短い形（具体的な操作は別途書く）：

> CALの操作は https://github.com/USXUSX/Calendar/blob/main/docs/chat-schedule.md の「通常操作の短い入口」に従ってください。

計測時だけ、この前に「最初のツール呼出しで時刻を記録し、準備を含めて保存確定結果の受取まで測ってください」を付ける。過去チャットの読了状態・対象ID・一時ファイルを前提にしない。長い手順を利用者が貼り直す運用や、新しい常駐・接続サービスは追加しない。

### 接続確認を一度に行う（#285）

選んだ接続経路で、以下の読取りを**一つの呼出し**として実行する。作業場所を指定できる経路ではその指定も使う。対象Macへの到達と必要ファイルを同時に確認し、正常ならdoctorや所在検索を追加しない。CLI自身も通常呼出しごとに既存DB・receipt表等を検証する。失敗・経路切替・所在変更時だけ必要な再確認を行う。

```sh
set -e
cd /Users/us/Tools/Development/Calendar_Dev
/usr/bin/python3 -B - <<'CAL_CONNECTION_CHECK'
import json
import socket
from pathlib import Path
root = Path('/Users/us/Tools/Development/Calendar_Dev')
cli = root / 'scripts/cal_schedule.py'
if Path.cwd().resolve() != root.resolve() or not cli.is_file():
    raise SystemExit('CAL checkout or CLI unavailable')
print(json.dumps({
    'host': socket.gethostname(),
    'cwd': str(Path.cwd()),
    'python': '/usr/bin/python3',
    'cli': str(cli)
}, ensure_ascii=False))
CAL_CONNECTION_CHECK
```

選択済みデバイス情報と返されたhostを照合し、対象Macと分かるまでwriteしない。host名が想定と異なる場合に自動許可しない。これは接続・所在の確認であり保存成功ではない。RDCのdevice IDや標準session IDを文書へ固定しない。継続出力の回収は[接続手順](#接続条件継続rdcへ戻す手順283)に従う。

## Chatで使う

対象Mac `usMac-miniM4Pro.local` の稼働と、ChatGPT側でそのMacへの標準実行経路が利用できることを確認する。Cloudのshellを対象Macと取り違えない。作業位置は `/Users/us/Tools/Development/Calendar_Dev`、Pythonは `/usr/bin/python3`、CLIは同checkoutの `scripts/cal_schedule.py`。`hostname`、`pwd`、Python・CLIの所在を読み取り確認し、以下の専用コマンドを使う。次の入口を最初に伝える（またはこの文書を読ませる）。

> 日程・タスクの操作は既存機能の範囲で接続済みMacの標準実行経路を優先し、利用できなければ既存RDCから `/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py` を使ってください。変更前に対象IDと最新revisionを取得し、要求IDと送信内容をチャットに残してください。応答不明時は同じ要求IDを照合し、別IDで追加し直さないでください。CALのcommitted receiptを受け取ってから保存済みと報告してください。未対応の依頼は未対応と伝えて追加案を提示し、登録依頼だけを根拠に機能開発へ進まないでください。

上記は接続の詳細説明であり、短い入口で確認済みの項目を再実行する手順ではない。その後は「10月8日9時に打合せを追加」「このタスクを完了」「開始を10時へ変更」等を依頼する。対象が曖昧ならread結果から特定してから操作する。候補の複数一致を勝手に1件へ絞らない。ChatはCALへ直接SQLを書いたり、別の即席更新スクリプトを作ったりしない。既存RDCの汎用実行権限は残る。専用CLIを使うことは運用規約でありRDCの技術的な権限制限ではない。

### 接続条件・継続・RDCへ戻す手順（#283）

標準経路には対象Macの稼働とChatGPT側のMac接続が必要。すべてのChat環境やアプリ終了中の利用を保証しない。「標準接続」は既存のRDC以外の実行経路を指し、インターネット中継なしや別の保存サービスを意味しない。Frameのブラウザ表示の条件とは別である。

| 経路 | 呼出し・継続・結果回収 |
| --- | --- |
| 標準Mac接続 | `exec_command`へ作業位置と上記Python・CLIを指定する。`session_id`が返れば同じIDの`write_stdin`で続きの出力を回収し、最終`exit_code`まで確認する。各回の出力をつなぎ、先頭だけ・最終chunkだけで判定しない |
| 既存RDC | RDCで同じ対象Macを選び、`start_process`から同じ作業位置・Python・CLIを呼ぶ。PIDが返れば、そのPIDの`read_process_output`で未回収出力と終了コードを取得する。出力のoffset・lengthと残りを確認する |

標準の`session_id`とRDCのPIDは交換できない。受付成功、途中出力、timeout、出力欠落・打切りを完了としない。出力上限を確認し、JSONの解析成功や末尾・exit 0だけで全文の一致を判断しない。#281の隔離比較では、大きい日本語出力のRDC受信に文字置換があった（保存値は健全、原因は未確定）。不一致があれば保存成功と推測せず、同一要求のlookupと再取得で確認する。

標準経路が使えなければ既存RDCを選び直す。送信済み・送信した可能性がある操作は、経路を変える前後で要求ID・送信内容・expected_revisionを保持し、まず同じIDでlookupする。結果不明の操作を新しいIDで並行実行しない。再送時も同一ID・同内容を使う。接続不可やアクセス拒否を設定変更・別権限で迂回しない。RDC本体や設定を変更・停止せず、経路を戻すための自動fallbackやmigrationは追加しない。

専用CLIの使用は両経路の運用規約であり、汎用実行権限の技術的な制限ではない。他ツールの経路は今回変更しない。

### 通常操作と機能開発の境界

通常の日程・タスク・旅程の登録／変更は、現行の専用CLIが提供する機能内で行う。既存機能で実行でき、対象と内容が明確な依頼には、毎回の追加確認を要求しない。

未対応の条件・操作なら、未対応であることと必要な機能追加案をusへ提示する。既存機能で可能な代案があれば、依頼との差分も示し、意図を変えた登録を勝手に行わない。日程登録依頼だけを根拠にコード変更・開発Issue／PR作成・merge・本番反映へ進まない。機能追加への明示指示がある場合に、現行TDSの通常開発手順で進める。各経路の汎用実行権限は機能開発の許可を意味しない。

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
- 例：「CAL保存済み。対象ID …、要求ID …、receipt …、revision …」。保存内容も短く示す。標準execのsession返却やRDCの「Process started」、Frame画面の表示だけで成功扱いにしない。保存確定を確認した時点で先に知らせ、続けてlookup・再取得と必要な反映確認の結果を返す。保存後照合が済む前に照合完了とは報告しない。
- 各経路の継続ハンドルから最終出力・終了コードを回収する。通信断・出力なし・timeout・`status=unknown`は結果不明。`lookup --request-id`で照合する。
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

`apply_schedule_request`はBEGIN IMMEDIATEの同じ接続内で、要求ID照合→現在行のrevision確認→既存`_change_schedule`→receipt保存を実施し、commit後にだけ成功を返す。Frameの`change_schedule`は単発をこの正式入口へ委譲し、更新・Validation・版照合・receipt保存を二重に持たない。`get_schedule_item`は現在値、`lookup_schedule_request`は元操作のreceiptを返す。lookupは外部送信しない。新規commitだけが`after_save`でGoogle反映を一度試み、再送は現在のローカルGoogle状態を返して送信しない。保存後送信前の中断やGoogle未反映は明示的なGoogle再試行で扱い、正式保存の再送で解消しない。試作subclassや故障注入は本番へ持ち込まない。

revisionは正本行全値（更新日時を含む）のSHA-256。連番ではなく内容fingerprintで、Frameや既存CRUDによる内容変更も検出する。読み取り後に値が変わって元の値・日時まで完全に戻った履歴の検出を保証するものではない。同時再送はSQLiteの書込みlockとrequest_id主キーで直列化する。

receiptは既存CAL DBの`schedule_receipts`に保持し、自動削除しない。元データとreceiptは同じbackup対象。別サービス・別DB・公開HTTP更新入口は追加しない。Googleの未反映・再試行・認証は[所有契約](google-calendar.md)へ集約する。CLIのreadは旅程loadを呼ばず、context/candidateに触れない。

## 配置・初回反映

標準接続先は既存Frameと同じ`/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3`。データrootも既存Calendar_Local。起動時にDBを作ったりmigrationしたりしない。`--database`と`--local-root`は合成テストの隔離用で、通常Chatでは指定しない。

既存DBへはSQLite backupを取ったうえで次の明示migrationを1回実行し、既存各tableの内容保持を確認する。再実行は変更なし。新規initializerにもreceipt表を含める。schema version 3を維持し、nullable列追加や既存行の変更はしない。

```sh
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/migrate_schedule_receipts.py /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3
```

通常のChatからmigrationやinitを実行しない。導入後はdoctorでreadyを確認する。CLI導入自体の切戻し時はCLI利用を止め、receipt表を削除せず保持する。#283の接続経路だけの切戻しでは同じCLI・DB・receiptを使い続ける。追加の常駐・RDC設定変更・認証変更は不要。

## 旅程の局所変更

名称・時刻・コメントなど、既存の意味操作で表せる変更は `trip-operation` を使う。最新 `trip-get` のTrip ID・対象stable ID・revisionオブジェクト全体をそのまま用いる。対象stable IDが分かる局所更新は、保存前・後続再取得とも `--item-id` で出力を絞る。Trip IDが既知ならtripsを重ねて実行しない。要求形式と対応fieldは[直接編集の正式要求](direct-schedule.md#画面の正式要求calendar-238)が正本で、CLIも同じCAL入口を呼ぶ。

予定の表示名変更なら `operation=item`、`source_type=scheduleItem`、`changes.title` を使う。complete Tripの `action` をそのままchangesのキーにしない。具体例・コメントの保持は[Chatからの局所変更](direct-schedule.md#chatからの局所変更)を参照する。対応済みのfieldだけを指定し、未知fieldを推測して送らない。

この経路ではCALがeffective Tripを検証し、対象fieldのOverrideとreceiptを同じtransactionで保存する。呼出側でcomplete Tripを組み直さず、変更しない地点をtrip-resolveし直さない。場所や予約を変更する依頼を、表示名だけ変更して処理済みにしない。`ai_instruction` の保存は未処理指示の記録であり、その実行や既存指示の消込みではない。

保存確定・要求ID・再送・競合拒否・後続照合は[共通の判定](#保存確定の判定と応答不明)を使う。未処理指示への対応を含め、局所操作では表せない変更には次節の全体保存を使う。

## 旅程の正式更新（#205）

同じCLI・同じlookup・同じCAL SQLite receipt表を使う。予定/Todoと旅程のJSON形式は別で、全旅程削除は提供しない。

- `trips`：登録済み旅程の一覧。対象IDを特定する。
- `trip-get --id <Trip ID>`：effective complete Trip、未処理instructions、revisionを取得する。Direct Overrideと固定自宅を含む。revisionはtrip_version/effective_hash/instructions_hashの組で、指示の追加・変更も競合判定に含める。
- `trip-get --id <Trip ID> --item-id <予定／移動のstable ID>`：同じ最新contextからMac上で対象1項目を抽出する。返すのは `trip_id / context_scope=item / trip_summary / day / source_type / source_item_id / item / places / bookings / instructions / revision`。`trip_summary` はID・名称・期間、dayはその日の概要で、他項目は返さない。placesは候補・選択・地図表示先・移動端点と関連予約の地点、bookingsは対象の予約ID・地点・移動に関係する予約。未処理instructionsは全件、revisionはTrip全体の元の値を保持する。対象不在・重複はexit 2で拒否する。無指定の出力は従来どおり。
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

`--item-id` の応答はcomplete Tripではなく、全体save・trip-resolveの入力には使わない。対象IDが不明なら無指定trip-getで特定する。前後の行動や他日の構成を判断する依頼も無指定で取得する。全件照合が必要な後続確認は、Mac上で無指定の応答を比較して判定結果だけ返すなど、全文をAIへ再送する必要はない。

create / saveを送る前に[共通生成ガイドの登録前チェック](trip-json-generation.md#登録前チェック)を行う。

これは形状例であり空tripは無効。新規登録はaction=create、expected_revision省略、handled_instruction_idsは空。更新はaction=saveと最新trip-getのrevisionを指定する。getのtripを出発点に意図した変更だけを適用し、既存ID・予約・選択済み地点・変更対象外の値を保持する。対応した指示IDだけを列挙する。新規createは既存ID・未登録の同名正式ファイルを上書きしない。

座標補完は既存CALのplan/result契約を再利用する。既存座標・手動補正・固定自宅設定を保持し、同一点をまとめて補完する。通常Chatは保存前に`trip-resolve`を実行し、その`coordinate_results`をそのまま`apply`へ渡す。検索対象ごとに結果キーが必要で、検索自体を省略した空`{}`や一部欠落は`coordinate_results_incomplete`で拒否する。検索を実行して結果がなかった地点は値nullとして明示し、その地点だけ未取得のまま保存できる。receiptのcoordinates（filled/missing/existing）と未取得の有無を報告する。必要な位置補正は既存Frame地図編集で行える。座標を推測して埋めない。

`trip-resolve`は既存Frameのloopback `map-config`からブラウザ用接続設定をメモリ内で取得し、Places Text Search (New)へ名称・住所／当日エリアの既存queryだけを送る。新しいcredential・常駐処理・providerは追加しない。接続設定自体をログ・receipt・Gitへ残さない。Frame接続または地図設定が利用できなければresolveを失敗として止め、未検索を空結果に読み替えて保存しない。

CALの共通Schema・semantic・Todo参照検証と、既存の`.adoption` staging/journal・SQLite transactionを使う。正式JSON置換前の中断は未採用へ、置換後はSQLiteのversion・指示・Overrideとreceiptを確定させて収束する。lookupは該当要求の未完journalを回復してからreceiptを返す。反映後の応答喪失でも元receiptを取得できる。復旧不能な不一致は確定済みと返さず、journalや正式ファイルを手編集しない。

旅程receiptは保存したcomplete Trip、revision、対応指示、座標補完件数も含む。正式JSON＋SQLite＋`.adoption`は従来どおり同じCAL LocalDataの管理対象で、別DBは作らない。receiptと保存データは非公開扱いでGit/Issueへ転記しない。

通常Chatのcontext/candidate授受、context自動共有、Frame load/reloadのcandidate自動採用は停止した。残存ファイルは削除しない。Frameの手動新規JSON取込、直接編集、Chat指示入力は維持する。旧Envelopeのdomain処理は保守・既存中断復旧用に保持するが、通常のChatから呼ばない。各経路の接続条件は本書の接続手順に従う。確認済み範囲と未観測は後述の#281 / #283の記録を参照する。

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

旅程画面の直接操作は[正式要求・版照合・receipt契約](direct-schedule.md#画面の正式要求calendar-238)を使用する。指示保存とAI処理、正式保存とview/Google/DSP反映を区別する。

## 鉄道経路の部分更新（#244）

新規complete Tripと既存saveは[railRoute契約](map-locations.md#国内鉄道路線の形状244)に従う。既存Tripの一部の鉄道指定だけを変える場合は、trip-getから最新revisionと対象Transport IDを取得し、`cal_schedule.py trip-operation` のstdinへ次の形式を渡す。show_on_mapは既存指定を尊重し、表示を依頼された区間だけtrueとする。

```json
{"request_id":"example-new-uuid","trip_id":"取得済みTrip ID","operation":"item","expected_revision":{"trip_hash":"取得したrevision全体をそのまま指定"},"values":{"source_type":"transport","source_item_id":"取得済みTransport ID","changes":{"rail_route":{"legs":[{"operator":"東日本旅客鉄道","line":"東北新幹線","from":"東京","to":"新白河","via":[]}]}}}}
```

上のrevisionは形式説明用。実行時はtrip-getのrevisionオブジェクト全体を改変せず使う。要求ID/送信内容を保持し、exit 0・committed receiptの要求ID/対象/values/revisionを照合、同じlookupから確定結果を再確認する。再送とstale拒否は既存正式要求と共通。路線名の自然言語解釈はChatで行い、分からない区間は指定せず未確定を報告する。CLIは正式JSON/DBの直接編集の代替となる所有入口である。

100名城の訪問状態・日付・コメントは別の[CAL城専用CLI](castles.md)を使う。日程applyへ混在させない。

## 任意の区間計測（#279）

通常はOFF。専用CLIのコマンド名より前に `--timing` を付けると、従来のstdout 1 JSON・exit codeを維持して、stderrへ `cal-timing-v1` の診断JSONを1行返す。`--timing-file /tmp/cal-timing.jsonl` は計測を有効にして同じ診断を指定先へ追記する。ファイルはGit管理外に置く。Git checkout内の指定や書込失敗ではファイル保存を省略し、正式操作の成否は変えない。親directoryは自動作成しない。

各呼出のランダムな `diagnostic_id` は正式request_idと独立する。関連する複数コマンドには同じ `--timing-group <UUID>` を明示できる。診断は操作名、status、resolution（new/replayed）、exit codeに対応するfailure_class、件数、monotonic clockの区間msとtotal_msだけを持つ。旅程本文・タイトル・住所・検索query・Secret・原文応答・receipt・正式IDやhashを出さず、正式payloadのhash・receiptへ計測値を混ぜない。

主な区間は以下のとおり。区間は入れ子になり、同名区間は複数回出現するため、全区間の単純合計をtotalと比較しない。区間のstatus=errorはその区間を例外で抜けたこと、最上位status/failure_classはCLIの返却結果を示す。

| 区間 | 対象 |
| --- | --- |
| input / domain_init | 入力JSONの取得・decode、CAL初期化 |
| trip_recovery / request_recovery | Tripの中断回復、要求に対応するjournal回復 |
| trip_get / revision_context / trip_read / trip_effective | 読取、正式JSON、Override・自宅・旅行情報を含むeffective合成とrevision取得 |
| trip_validation / location_plan / coordinate_completion | Schema・意味検証、地図補完plan、保存時の結果適用 |
| location_resolve / map_connection / places_search | resolve全体、Frame接続設定取得、個別Places検索。現行の直列検索・同queryのcacheを維持 |
| trip_apply / lock_wait / revision_check | 保存処理、BEGIN IMMEDIATE待ち、create対象・save版照合 |
| formal_json_journal / receipt_finalize / db_commit / db_rollback / journal_cleanup | 正式JSON・journal、DBへのreceipt等の書込、transaction終了、確定後のjournal整理 |
| post_commit_notification / post_commit_google_sync | commit後の通知とGoogle同期試行（未設定ならその確認時間）。応答待ちに含まれる |
| post_commit_google_status / lookup | replay時のGoogle状態取得、今回のreceipt照合。元保存時間ではない |
| response_prepare / response_write | stdout JSONの準備と書出し |

`total_ms` は引数解析後からstdout書出しまで。Python起動・import・引数解析、診断自身の出力、標準接続／RDCの起動・通信・結果回収、Chat調査・AI推論・確認待ちは含まない。`committed_at`は確定日時であり所要時間ではない。計測中の例外でも取得済み区間を返すが、強制終了・電源断で最終診断を返せない場合はある。応答不明時は従来どおり同じrequest_idでlookup／再送し、今回の診断と元保存を区別する。

### 合成測定の再実行

```sh
python3 -B scripts/measure_chat_timing.py --output /tmp/calendar-synthetic-timing.json
```

既存Samplesを基に、小規模create、タイトルだけのsave、地点・行動件数を増やしたcreateを比較する。全てのDB・Trip root・Chat rootは明示した一時directory内。外部通知／同期は未設定、ネットワーク接続はtest guardで禁止し、実credentialやCalendar_Localは使わない。正式応答は契約照合にのみ使い、出力ファイルには診断と集計だけを保存する。

各条件で初回1回と後続3回（中央値・範囲）を記録し、fresh保存、同一要求のreplay、lookup、trip-getを分ける。毎回別の一時DB・fresh Python processを使う。「初回」は最初の観測でありOS cacheを消去したcold測定ではない。process_wall_msは起動・import・test guard・出力取得・終了を含むローカルsubprocess時間で、RDC時間やAI推論時間へ読み替えない。

区間値・失敗・mockされた地図／通知／同期待ちの切分けは `Tests/test_chat_timing.py` で確認する。RDC実往復を行う場合は既存verbose_timingのtotal・time-to-first-output・exit detectionのうち取得できた値を別記し、PID返却後のread_process_outputも記録する。コマンド間の空白をAI推論時間と断定しない。合成結果は実地図API・実Google同期・本番データ量・実Chat全体の性能を証明しない。

## Chat実行開始から反映までの経路計測（#281）

CAL内部計測だけでChat全体を完了扱いにしない。正式保存・Google反映・Frame API・利用端末の表示は別の到達点である。ブラウザAI生成はこのChat→標準Mac接続またはRDC→CLI経路と混ぜない。

### 既存の確認結果と残る観測（#283）

[#281の隔離比較結果](https://github.com/USXUSX/Calendar/issues/281#issuecomment-6800633876)を再利用する。同じMac・Python・CLIで保存、receipt照合、同一ID再送、競合拒否、中断模擬からの回復、長い日本語入出力を確認済み。実通信断や機器・アプリ停止を確認したものではない。

[#283](https://github.com/USXUSX/Calendar/issues/283)には、2026-11-12のiPhone発の通常会話で標準接続から実旅程のコメント・列車情報を更新し、正式保存・指定箇所の差分・再取得・Frame API反映を確認、usのiPhone表示確認も得たことが記録されている。この実更新を未確認扱いにしない。隔離試験とは到達点を分け、試験や完了済み更新を繰り返さない。

2026-11-12の合意により、当面の短縮対象は**最初のツール呼出しでの時刻取得から、保存確定結果の受取まで**とする（#285）。新規チャットの手順取得・接続確認・操作選択を含む。指示送信から初動までと保存報告の端末表示は主指標から外し、未観測を0としない。#281で未完とした元の端末表示までの全体観測は、この目標変更や文書整備で達成した扱いにしない。

標準Mac接続とRDCを併存する。通常チャットで使うRDCも改善対象に残し、Dots固有の待ちとブラウザAI経路は別の検討対象とする。現状50秒以内は許容できるが50→30秒程度の改善には価値がある、1秒以内の処理を追わず10秒規模の区間を優先する、という規模感で判断する。最短記録や詳細な原因分離を目的にせず、小さい変更で区間全体が短縮したかを見る。

### 新規チャットでの短縮確認（#285）

主な効果確認はiPhoneの通常チャットからRDC経由で行い、**毎回新規チャット**に同じ入口参照と同程度の具体的な操作指示を渡す。標準接続で行った結果をRDCの改善実績に混ぜない。同じチャットの連続実行・時間を置いた再開は条件として区別する。過去の異条件の47秒等は参考値であり、今回の同条件baselineにはしない。比較や本番の計測専用更新を反復しない。

1. 最初のツール呼出しの先頭で、通常準備より前に開始時刻を記録する。code modeなら `store("cal_setup_started_at_ms", Date.now())` のように呼出元で保持し、その後同じ操作内で通常のツールを使う。時刻取得だけのMac往復や、事前に手順を読み込む準備runを追加しない。先に完了した準備がある場合はその範囲を明記する。
2. 短い入口から必要な節を読み、接続確認・最新対象取得・操作選択・保存を行う。取得／保存等の通常呼出しの前後を同じ呼出元の時計で記録できる範囲で添え、呼出間も含める。計測のために別の重い往復を増やさない。正式要求には従来の要求ID・revisionを使い、必要なら既存 `--timing --timing-group <UUID>` を再利用する。
3. session／PIDが返った場合は同じハンドルの最終出力・終了コードまで回収する。**保存確定出力を受け取った直後**を終了時刻として保持し、exit 0・committed receiptの一致を満たした結果に限って採用する。Macの `committed_at` やプロセス起動応答を「結果の受取時刻」で代用しない。
4. 終了−開始を「初動→保存確定結果受取」として、経路・新規チャットであることと共に保存完了報告へ添える。保存確定を先に知らせ、その後lookup・再取得・必要なFrame反映を照合する。後続照合は別区間で、主指標へ加えない。開始準備・保存前・保存呼出しの内訳があれば、未分類を含め隣接区間で全体へ積み上げる。AI推論・純通信へ無理に分解しない。
5. 秒単位の目安で十分。可能なら同一の持続する単調時計を用いる。`Date.now()` は呼出元の壁時計なので時刻補正があれば不採用にし、異なる端末・Macのtimestampを直接差し引かない。開始や受取境界を記録できない環境では未取得の試行を速度判定に使わず、その場で同じ試験を反復しない。測定可能な呼出元を先に決める。

必要な具体的更新だけを行う。保存後チェックの優先度は低いが、定型処理をAIからMacへ移す別の改善を行う場合はチェックも含めて検討する。今回の入口整備は定型処理移管や後続チェック削除を実装するものではない。

記録は段階名・数値・状態・ランダム診断IDだけとし、本文・住所・query・credential・原文receiptをログ／Gitへ残さない。RDC設定、モデル、新規常駐・監視DB・外部ログを変更しない。詳細な原因解明より、利用上の待ちが短くなったかを判断する。

### 隔離した旅程経路の確認

`scripts/measure_chat_route.py` はRDCへ各段階を**別の呼出**として送るための合成fixture。通常のChat実行やAI作成を再現したものではない。空の一時rootを明示してprepareし、以降同じroot・caseで実行する。

```sh
python3 -B scripts/measure_chat_route.py --root /tmp/cal-route-unique prepare
python3 -B scripts/measure_chat_route.py --root /tmp/cal-route-unique --case small-save acquire
```

caseは `small-save`、`small-create`、`large-create`。`acquire → draft → resolve → apply → lookup → reread → frame` を各々RDCのstart_processから送る。`draft` はMac上の決定論的な合成案準備でありChat推論ではない。`frame` には `--frame-source <現行FrameのGit checkout>` を明示し、既存Frame用のPython環境を使う。既存FrameのadapterとHTTP handlerを一時loopback serverで起動し、effective APIのrevision・no-storeを確認して終了する。HTTP取得時間はserver起動／終了を除く別区間。これは隔離したFrame APIの確認であり、本番の既存process／公開画面／端末表示の反映確認ではない。

DB・Trip root・Chat root・要求・原文応答の照合用状態は全て指定した一時root内。地点座標は架空値を事前設定するため、実地図接続・検索は未実施。CLIの外部接続はguardで禁止、通知／Google同期は未設定。Frameは一時loopbackへのreadだけを許可し、既存の運用process・公開先・認証・LocalDataを変更しない。`replay` と `stale` は保存後の追加確認用で、前者は元receipt一致、後者は版競合拒否を確認する。

`route.jsonl` とstdoutにはallowlistの診断・照合結果のみを出す。CAL内部totalとは別にfixtureのCLI subprocess wallを同じprocess内のmonotonic時計で測る。Pythonのmonotonic timestampを異なるprocess間で直接比較せず、外側マークは同じ持続する呼出元processで採る（予備観測ではMacのPython 3.9にprocess間の原点不一致があった）。呼出元の時計マーク自体を別ツールで採る場合、その記録コストも含む**境界を囲う時間**として表記する。異なる時計のtimestampをつないで全体timelineを作らない。

合成fixtureのRDC往復が通っても、通常Chat開始・実際の案作成・実検索／Google同期・本番Frame・端末表示は証明されない。これらが未観測ならIssue #281のend-to-end実測は未完として残す。fixtureの確認だけを根拠に改善範囲を広げず、入口整備は#285の範囲で扱う。ブラウザ性能対応は別途判断する。
