# CAL → Google Calendar（#213）

CALの正式保存が先、Googleの反映は後。Frame・RDC専用CLIは同じCAL処理を使う。
receiptはCAL保存確定の証拠で、応答の`google`は別の反映結果。
Google障害・未認証でも保存を取り消さない。新しい常駐、定期ジョブ、DB、汎用queueは追加しない。

## 表現と範囲

専用「CAL」の確定calendar IDのみ使用。同名の既存カレンダーは採用しない。
旅行は期間の終日1件とFrame旅程リンク。通常Event/Todoは全件、完了Todoは件名に✓。
初回実行日のAsia/Tokyo当日以降の通常予定・タスク、継続中／今後の旅行が対象。
登録済み対応項目は過去になっても変更・削除へ追随する。Googleだけの項目や既存カレンダーへ触れず、件名だけで同一予定を判定しない。

時刻ありは既存Eventのtime_zoneを保持し、未指定/定期はAsia/Tokyo。
時刻なしは終日（Googleのend.dateは翌日排他的）。終了不明は1分の開始マーカーにして
「終了不明（1分の開始マーカー）」を説明へ付ける。メール登録の既存Mac API実装はないため、
Chat接続側の実装に依存せず、Googleの必須start/endに対する最小表現として採用。
明示的な開始＝終了も1分マーカーと説明にし、CALの終了値は変えない。

daily/weekly/monthly/month_end/yearlyはRRULE（BYDAY、BYMONTHDAY、月末=-1、年次BYMONTH/BYMONTHDAY）。
31日と2/29は無効日をスキップ。CALの各segmentを独立masterへ写し、今回以降変更は元masterのUNTILと新masterで表す。
単回移動・変更・完了は元masterにEXDATE、独立した例外イベントへ写す。削除はEXDATEのみ。
無期限は無期限RRULEであり有限窓の定期更新を要しない。初回は最初の対象回までDTSTARTを切り上げる。
初回以前の回は作らず、登録済みseriesの範囲内では過去例外も追随する。

[Googleの繰返し/EXDATE仕様](https://developers.google.com/workspace/calendar/api/concepts/events-calendars)、
[イベント仕様](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)、
[OAuth Desktop手順](https://developers.google.com/identity/protocols/oauth2/native-app)に従う。

## 状態・共通契約

既存SQLiteの`google_events`にCALキー、送信前に確定したランダムevent ID、初回下限日、反映済みhash、秘密を含まない失敗理由を保持。
`google_calendar_meta`は初回calendar IDを固定し、無断の送り先変更を拒否。
HTTP前にCAL transactionを終了し、既存DB横のlockでCLI/Frameの送信を直列化。
応答喪失は同じIDのGETと所有markerで照合。所有markerが違うイベントは変更・削除しない。
削除の対応付けも保持。Google取得結果は照合用で、CALへ取り込まない。

- `google_status()` → `status=synced|unreflected`, `pending`件数、`reason`。対象期間に依存せず削除分も含む。
- `sync_google()` → 同じ状態。未反映だけ手動再試行。
- `sync_google(reconcile=True)` → 対応イベントをGETして照合・CALから再反映。Google単独項目は対象外。
- 保存API/CLI応答の`google`は上記の状態、receipt内へGoogle結果を混ぜない。

```sh
python3 scripts/cal_schedule.py google-status
python3 scripts/cal_schedule.py google-retry
python3 scripts/cal_schedule.py google-reconcile
```

自動反映は通常画面/Chatの保存完了後。読み込みだけでは送信しない。
送信中に別の保存があれば差分は状態へ残り、次の保存または再試行で反映する。
Google側の手編集は手動照合または次のCAL変更時にCALの値で戻る。

## 初回設定（本人操作）

ChatのGoogle接続はMac OAuth credentialとして使わない。
既存Google CloudプロジェクトでCalendar APIを有効化し、Google Auth PlatformでDesktop appのOAuth clientを用意する。
外部アプリのTestingでは本人をtest userへ追加する。Testingのrefresh tokenには期限があるため、
継続利用では本人用アプリの公開状態と[Google OAuth制限](https://developers.google.com/identity/protocols/oauth2#expiration)を確認する。
要求scopeは`calendar.app.created`（アプリが作成する専用カレンダーのみ）。既存全体/プライベートへの権限は要求しない。

1. Desktop client JSONをMacの`Calendar_Local/settings/google-client.json`へ置く。値はChatへ貼らない。
2. Terminalで下記を実行し、ブラウザで対象Googleアカウントを選び、権限を確認して許可する。

```sh
cd /Users/us/Tools/Development/Calendar_Dev
chmod 600 /Users/us/Tools/LocalData/Calendar_Local/settings/google-client.json
python3 -B scripts/cal_google_setup.py authorize
```

PKCE/state/loopback callbackを使い、refresh tokenはprivate localの0600ファイルへ保存。
認証後はCodexが`create-calendar`で新しい専用CALを作りIDを保存し、`probe`で一時イベントの追加・変更・取得・削除を確認する。
作成応答が不明なら自動再作成せず、Google側で作成結果とIDを確認する。
初回実データ反映は`google-retry`、続いて`google-reconcile`と件数・反映済み状態を確認。
実日程本文やcalendar ID/tokenをIssue・PR・Gitへ記録しない。

## 既存環境反映

DBをSQLite backupでprivate localへ退避し、`scripts/migrate_google_calendar.py <既存DB>`を実行。
既存テーブル/値が変わらず2表だけ追加されることを確認する。
merge済みCAL/Frameを公式同期し、[既存Frame再起動](operation.md#calコード変更のframe反映)と代表APIを確認する。
認証未完了時も通常保存は使える。初回Google反映・公開画面・物理iPhone受入は別に記録する。

## Gmail既存予定の重複回避（#221）

旅行関連Event/Todoも集約せず個別反映する。日付のある独立旅行は従来の終日旅行1件として反映し、日付未定は送信しない。旅行関連項目のsourceリンクは旅行詳細の識別子を使い、メール参照もdescriptionへ添える。

Chatの既存Google接続でメール根拠・予約対象・日付時刻の一致を確認したgoogle_calendar_id / google_event_idはCALが保存する。初回同期はその外部予定を参照済みとして記録し、CAL専用カレンダーへ重複POSTしない。外部予定に所有markerを付けず、変更・削除しない。Mac OAuth権限はapp.createdのまま。CAL管理イベントの応答喪失照合・marker・対応付けは維持する。

この参照は外部予定への書込み成功を意味しない。件名・日付時刻等を後からCALで変更して既存予定と一致しなくなる場合は、明示された新しい照合参照がなければ旧参照を解除し、変更後をCAL専用予定として送信する。外部旧予定は保持する。メモ/category/旅行関連だけの変更では参照を保持する。外部旧予定の整理は所有者判断とし、CALから削除しない。
