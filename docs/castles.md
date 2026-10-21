# 100名城の正式記録（#252）

CALの既存SQLite内の `castles` が100城のマスターと各城1件の訪問記録を所有する。番号・名称・県・市区町村・座標はFrame #368/#371の採用値を保持する。位置出典は既存の日本城郭協会案内のGoogleマイマップ。訪問履歴の複数件化、写真、一般観光地・旅程への自動接続は今回対象外。

`list_castles()` / `get_castle(int)` はid、name、prefecture、city、longitude、latitude、visited（boolean）、visit_date（ISO日付またはnull）、comment（文字列）、revisionを返す。日付なしの訪問済は許容する。未訪問へ戻すときはvisit_dateもnullにする。コメントは状態変更でも保持。UIでは保存値を表示し、未登録コメントを推測しない。

## Chat / RDC

既存RDCから `/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_castles.py` を呼ぶ。`read` で一覧・対象特定、`get --id 69` で現在値とrevision取得。`apply` の標準入力へ次のJSONを渡す（合成形式例。依頼なく実行しない）。シェルでは引用付きhere-documentを使う。

```json
{"request_id":"new-uuid","id":69,"expected_revision":"castle:69:1","values":{"visited":true,"visit_date":"2026-10-21","comment":"地点コメント"}}
```

valuesは変更fieldだけ。マスターの変更や新城追加はこの入口では提供しない。保存は `apply_castle_request`、照合は `lookup_castle_request` / CLI `lookup --request-id <ID>`。画面も同じ意味APIを使い、DBを直接扱わない。

BEGIN IMMEDIATE内で要求ID→revision→記録→receiptを処理しcommit後にだけ `status=committed` を返す。同じID/内容は元receiptを返して再更新しない。ID/内容違いは `request_id_payload_conflict`、古いrevisionは `revision_conflict`。revisionは城ごとの連番で、別城の編集は競合しない。receiptは更新時点のitem・要求ID・receipt ID・更新前後revision・時刻を保持する。現在値はgetを使う。GoogleやDSPへの配送は伴わない。

exit 0とcommitted receiptの対象・内容一致で保存確定。競合exit 3、入力拒否exit 2、応答不明/storage exit 5。lookup未検出はnot_found/exit 4で未実行を断定しない。結果不明時は同じIDを照合し、必要なら同じ内容で再送する。別IDで保存し直さない。正式ファイル/SQLの直接編集は禁止。CLI --database/--local-rootは合成検証用。

## 初回移行・反映

明示migrationのみ。起動時やChat操作時に自動導入しない。既存DBのSQLite backup後、次を一度実行する。

```sh
/usr/bin/python3 -B scripts/migrate_castles.py /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3 /Users/us/Tools/Development/Frame_Dev/frame_server/static/castle-prototype-data.js
```

ソースのJSON literalだけを解釈し、JavaScriptを実行しない。100番号を確認し、名称・位置はそのまま、日付はISOへ正規化、空欄は未訪問、コメントは空で保存する。既存城があればマスター一致を確認するだけで訪問記録を上書きしない。不一致は停止。旅程・旅行・既存tableを変更しない。再実行しても記録保持。新規initializerは空の城tableを作る。

両mainの公式同期後、既存 `com.usxusx.frame` 再起動でCAL/Frameコードを反映。公開先・認証・Job・通知設定は保持。read/lookupのみで本番確認し、実記録に試験保存をしない。切戻し時は編集を停止して旧ソースへ戻し、城とreceiptのtableを削除しない。backupは同じ既存CAL管理対象。物理iPhoneの操作評価は本人確認として別記する。

最小検証: `sh Tests/castles.test.sh`（合成100件、状態・日付・コメント、再実行保持、競合、再送/照合、実CLI）。
