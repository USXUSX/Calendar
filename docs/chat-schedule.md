# Chatからの通常予定・タスク保存（Frame #177 Phase 3 Step 1 / CAL #203）

既存Remote Desktop Commander（RDC）でMacのCAL専用CLIを呼ぶ。CALの既存SQLiteが唯一の正本。Frameを開く／再読込することは保存条件ではない。旅程のcontext/candidate・正式Trip JSONの経路は変更しない。定期日程・Google反映はこのコマンドの対象外。

## Chatで使う

ChatでRDCを選択し、対象Mac `usMac-miniM4Pro.local` を選ぶ。次の入口を最初に伝える（またはこの文書を読ませる）。

> 日程・タスクはRDCから `/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py` を使ってください。変更前に対象IDと最新revisionを取得し、要求IDと送信内容をチャットに残してください。応答不明時は同じ要求IDを照合し、別IDで追加し直さないでください。CALのcommitted receiptを受け取ってから保存済みと報告してください。

その後は「10月8日9時に打合せを追加」「このタスクを完了」「開始を10時へ変更」等を依頼する。対象が曖昧ならread結果から特定してから操作する。候補の複数一致を勝手に1件へ絞らない。ChatはCALへ直接SQLを書いたり、別の即席更新スクリプトを作ったりしない。既存RDCの汎用実行権限は残る。専用CLIを使うことは運用規約でありRDCの技術的な権限制限ではない。

### 読み取り・照合

```sh
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py doctor
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py read --start 2026-10-01 --end 2026-10-31
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py get --kind todo --id '取得済みの対象ID'
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_schedule.py lookup --request-id '送信時の要求ID'
```

`read`は両端を含む期間の通常予定・日付付きタスク（完了を含む）を返す。`get`は対象の全保存値とrevisionを返す。日付なしの既存Todoは期間readの対象外だがIDによるgetは可能。`doctor`のreadyは接続・receipt表の準備確認であり、保存成功ではない。日時は既存CALと同じローカル日付と24時間表記（通常運用Asia/Tokyo）。日付ISO `yyyy-mm-dd`、時刻`HH:mm`、任意値の解除はnull。

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

追加以外では、同じJSONに`id`と`expected_revision`を必ず付ける。両方とも直前のread/get結果を使う。件名や日付をIDの代わりにしない。既存共通処理により空の件名・不正日時・終了が開始より前・未対応field等を拒否する。旅程の更新は受け付けない。

```json
{"request_id":"example-replace-with-new-uuid","kind":"todo","action":"complete","id":"取得済みID","expected_revision":"sha256:取得した値","values":{"completed":true}}
```

### 保存確定の判定と応答不明

- exit 0と`status=committed`、かつreceiptの要求ID・対象・操作・内容が一致して初めて保存確定。`receipt_id`、`entity_id`、`revision`（削除後はnull）、`committed_at`を結果として会話へ残す。削除receiptは削除前の内容とprevious_revisionを保持する。
- 例：「CAL保存済み。対象ID …、要求ID …、receipt …、revision …」。保存内容も短く示す。RDCの「Process started」やFrame画面の表示だけで成功扱いにしない。
- RDCがPIDを返したらread_process_outputで終了・出力を取得する。通信断・出力なし・timeout・`status=unknown`は結果不明。`lookup --request-id`で照合する。
- lookupがcommittedなら元の確定receipt。`not_found`（exit 4）は現時点で確定receiptが見つからないだけで、未実行の証明ではない。同じ要求ID・同じ内容で再送できる。別IDで再作成しない。
- 同一ID・同一内容の再送は`resolution=replayed`で元receiptを返し、二重更新しない。削除後や後続変更後でも元の操作結果を返す。**receiptはその操作時点の結果**であり、現在値が必要ならgetで読み直す。
- 同一ID・異なる内容は`request_id_payload_conflict`（exit 3）で拒否。revision不一致は`revision_conflict`（exit 3）。最新内容を取得し、依頼と照らして内容を再確認した別操作には新しい要求IDを使う。staleを無条件上書きしない。
- 入力拒否はexit 2。ストレージ利用不能等はexit 5/result unknown。保存できたと推測せず照合する。拒否された操作のreceiptは作らない。

## 所有・transaction・revision

`apply_schedule_request`はBEGIN IMMEDIATEの同じ接続内で、要求ID照合→現在行のrevision確認→既存`_change_schedule`→receipt保存を実施し、commit後にだけ成功を返す。Frameの`change_schedule`も同じ更新・Validation本体を使う。試作subclassや故障注入は本番へ持ち込まない。

revisionは正本行全値（更新日時を含む）のSHA-256。連番ではなく内容fingerprintで、Frameや既存CRUDによる内容変更も検出する。読み取り後に値が変わって元の値・日時まで完全に戻った履歴の検出を保証するものではない。同時再送はSQLiteの書込みlockとrequest_id主キーで直列化する。

receiptは既存CAL DBの`schedule_receipts`に保持し、自動削除しない。元データとreceiptは同じbackup対象。別サービス・別DB・公開HTTP更新入口・Google連携は追加しない。CLIのreadは旅程loadを呼ばず、context/candidateに触れない。

## 配置・初回反映

標準接続先は既存Frameと同じ`/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3`。データrootも既存Calendar_Local。起動時にDBを作ったりmigrationしたりしない。`--database`と`--local-root`は合成テストの隔離用で、通常Chatでは指定しない。

既存DBへはSQLite backupを取ったうえで次の明示migrationを1回実行し、既存各tableの内容保持を確認する。再実行は変更なし。新規initializerにもreceipt表を含める。schema version 3を維持し、nullable列追加や既存行の変更はしない。

```sh
/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/migrate_schedule_receipts.py /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3
```

通常のChatからmigrationやinitを実行しない。導入後はdoctorでreadyを確認する。切戻し時はCLI利用を止め、receipt表を削除せず保持する。追加の常駐・RDC設定変更・認証変更は不要。
