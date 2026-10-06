# 通常予定・Todoと期間表示（#198 / Frame #177 Phase 2）

CALが通常Event/Todoの正本と検証・保存を所有し、Frameが月間・一覧・複数月と直接操作を提供する。SQLiteとformal/effective Tripの責務は維持する。

## 意味境界

- `read_schedule(start, end, include_completed=False, include_trips=True)`：両端を含むISO日付期間。登録済みTripはeffective `dateRange`の1件、通常Eventは期間と重なるもの、Todoは期間内の未完了かつ日付付きのものを返す。旅行内の予定は展開しない。Trip選択肢も返す。include_trips=Falseでは旅程を読み込まず通常Event/Todoだけを返す。通常項目には正本行の内容ハッシュrevisionを付ける。候補採用・context生成等の書込みを伴わない。include_completed=Trueのときのみ完了Todoもcompleted_at付きで返す（Frame #189の一覧用）。
- `change_schedule(kind, action, item_id=None, values={}, expected_revision=None, request_id=None)`：kindはevent/todo、actionはsave/delete/complete。saveはID省略時にCALがUUIDを採番、指定時は既存対象を更新し、未指定fieldは保持する。completeはTodoの明示booleanを受ける。既存参照を壊す削除は拒否する。保存は単一SQLite transactionのcommit後に結果を返す。定期回IDではexpected_revisionを必須とし、scope=thisの共通定期処理でreceiptを返す。request_id省略時はCALが採番する。画面からfollowingや条件の変更は受け付けない。
- Event入力：title/start_date/start_time/end_date/end_time/notes/trip_id。Todo入力：label/due_date/due_time/notes。任意値はnullで解除。空の件名、不正日時、終了が開始より前、存在しないTrip参照、未対応fieldは保存しない。新しい画面から作るTodoは日付必須。既存の日付なしTodoは削除せず保持し、今回の画面対象から除く。
- 週開始は日曜、完了Todoは月間・複数月・日別で非表示、一覧では完了チェック付きで通常の日時順に表示（Frame #189）。Chatのreceipt/revision契約は[正式Chatコマンド](chat-schedule.md)を参照。定期日程の条件・保存契約は同文書の#207節を参照。Google連携は[専用一方向連携](google-calendar.md)を使う。従来CRUDは保持する。

## 追加schemaと既存値保持

v3基盤への追加拡張としてevents.trip_id（nullable、tripsへの外部キー）とtodos.notes（nullable）を追加する。既存行は全値を保持し、追加値だけnullとなる。基本schema versionは3を維持し、追加列の存在で適用を判定する。新規initializerは拡張を含む。

既存DBへの適用は対象pathを明示する。通常read/サーバー起動で暗黙migrationしない。スクリプトは既存v3を要求し、新規DBを誤作成しない。2列は一transactionで追加、再実行は変更なし。

```sh
python3 scripts/migrate_schedule.py /explicit/path/to/calendar.sqlite3
```

本番適用時は現行DBをSQLite backupで保存してから追加し、旧行の値と件数が保持されたことを確認する。削除・再構築・Trip JSON移行はしない。旧版コードへ戻す場合も追加列を保持できるが、旧`create_event`は列数固定INSERTなのでその呼出しには互換性がない。取り消しは新規書込み前のbackup復元判断が必要になる。

定期日程は同じperiod readに各回を含める。通常項目fieldにseries_id・occurrence_date・シリーズrevisionを加える。完了フィルタと並び順は単発と共通。既存DBにはbackup後に `scripts/migrate_recurrence.py <既存DBパス>` でschedule_seriesを追加する。詳細は[Chat保存契約](chat-schedule.md)に集約する。

## 独立した旅行管理（#221）

`list_travel()`は全旅行を返す。`get_travel(id)`は基本情報と関連Event/Todo（期間内の定期回を含む）を返す。`change_travel(values, item_id=None, expected_revision=None, request_id=None)`は共通receiptで保存する。更新は最新revision必須。

基本情報はtitle、start_date/end_date、date_status（confirmed / tentative / undecided）、transport（air / rail / ship / car / other）。undecidedは両日付null、tentativeは仮日付あり。readにはtrip_id、dateRange、has_itinerary、itinerary_id、revisionを含む。日付未定は期間グリッドに出さず全旅行一覧に残す。`list_trips()`は旅程接続済みだけを返す。

旅行は既存trips registry内に先行作成し、`travel_basics`が基本情報の正本になる。旅程create/importは同じIDの未接続旅行へ接続する。同名・同期間（または日付未定）の未接続旅行が別IDにあれば重複登録を拒否し、その旅行IDを使う。既存旅程はmigrationで1対1に接続する。

旅行名と期間の表示は管理情報を使う。旅程JSONの日別行動日付は旅行基本情報の変更だけでは移動しない。日付未定でも既存旅程を保持する。Trip専用saveで明示変更された名称・期間は同じCAL基本情報へ反映し、別正本を作らない。保持する旧candidate採用は旅行基本情報を上書きしない。

Event/Todoに共通category、gmail_url、trip_idを追加する。categoryはgeneral（既定）、air、rail、ship、car、lodging、food、reservation、medical、finance、anniversary、pet、other。iconは保存しない。Chatは入力・メールの意味からcategoryを選び、CALは分類を推測しない。trip_id=nullで解除。Frameはcategoryだけ編集し、旅行関連は保持する。gmail_urlは`https://mail.google.com/mail/u/0/#all/<message-or-thread-id>`等のメール参照URL。本文は保存しない。

既存Google予定と同一と確認済みの場合のみ、google_calendar_id / google_event_idの組をgmail_urlと共に渡せる。Google連携の扱いは[所有文書](google-calendar.md)を参照。

既存DBはSQLite backup後に `python3 -B scripts/migrate_travel.py <既存DB> <Calendar_Local root>` を明示実行する。v3の既存値・receipt・定期条件・Google対応付けを保持し、新しいnullable列と既定general、travel_basicsだけを追加する。再実行は既存基本情報を上書きしない。通常起動でmigrationしない。
