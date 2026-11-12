# Chat保存までの時間ログ

通常の保存では、[短い入口](chat-quick.md)の呼出元計測をMacのCalendar_Local/logs/chat-save-timing.jsonlへ1操作1行で追記する。CALの保存やreceiptとは別の診断ログで、Git配信・新しい常駐・DB・外部サービスは使わない。過去の試験値は後付けしない。

## 記録する流れ

1. 最初のツール呼出し冒頭の呼出元時刻を保持する。Git取得、Mac取得、保存など各ツール呼出しの直前と応答直後も同じ呼出元時計で保持できる範囲で記録する。
2. 完全な一致committed receiptを最初に受信した直後をsaved_at_msとして保持し、保存完了と経過秒数を先に回答する。終了コード確認や照合まで時計を進めない。
3. 報告後の既存Mac実行（lookup・対象再取得）の先頭に記録コマンドをまとめる。記録のためだけの実行・接続・往復は追加しない。記録が失敗しても照合は続け、CAL更新を再送しない。
4. 記録と照合が正常なら追記報告なし。記録失敗・照合異常・確認不能だけ追加報告する。最終出力・終了コードは同じハンドルで回収する。

記録専用コマンドは次の形式。数値は形式説明用の合成値であり、実行時は今回保持した呼出元の値と要求ID/receipt IDを使う。

```sh
cd /Users/us/Tools/Development/Calendar_Dev
/usr/bin/python3 -B scripts/record_chat_timing.py <<'CAL_TIMING' || cal_timing_failed=1
{"clock":"caller_epoch_ms","started_at_ms":1000,"saved_at_ms":12500,"route":"rdc","operation":"trip_item","request_id":"synthetic-request","receipt_id":"synthetic-receipt","calls":[{"phase":"git","started_at_ms":1000,"received_at_ms":4000},{"phase":"read","started_at_ms":7000,"received_at_ms":8000},{"phase":"save","started_at_ms":12000,"received_at_ms":12500}]}
CAL_TIMING
# 続けて、同じ実行内で今回のlookup・対象再取得を行う。
```

callsは観測できた呼出しだけを時刻順に並べる。phaseはgit/read/save等の短い操作ラベル。記録のためにGitやMac取得を増やさない。routeはrdc / standard / mixed、operationはtrip_item / trip_save / event等の短いラベルとする。本文・名称・住所・変更内容・Secretは渡さない。

## 値の意味と制限

schema=cal-chat-save-timing-v1。elapsed_ms=saved_at_ms−started_at_ms、call_wall_msはcallsの各受信−呼出し直前の合計、unclassified_msは全体から呼出し合計を引いたもの。各callの元時刻・duration_msも保持する。内訳と未分類を足すと全体に一致する。recorded_atはMacで追記した日時であり、経過時間の計算には使わない。

caller_epoch_msは同じ持続する呼出元のエポックミリ秒（例: Date.now()）。異なるMac/端末時計を混ぜず、時刻補正が判明した試行は使わない。コマンドはclock指定、数値の有限性、時刻順序、未知fieldを検査するが、申告された時刻の取得元までは証明しない。呼出元時刻を記録できなかった場合は推定値でログを作らず、回答に計測不可と表示する。calls未取得なら空配列にし、全体を未分類として残せる。

call_wall_msには通信・ツール実行・応答返却が混在する。unclassified_msには準備・結果の解釈・次の要求作成・呼出し間の待ち等が混在する。いずれも純通信時間やAI推論時間と断定しない。指示送信→最初のツール、報告の画面表示、後続照合は保存までの経過時間に含めない。

複数の呼出元が同時記録してもflock付き追記で行を混ぜない。正常はstatus=recorded、失敗はstatus=failed/非0。このコマンドはCALのDBを開かず、正式保存・receipt・Google同期の成否を変えない。ログの自動削除・集計画面・詳細な内部計測の常時有効化は追加しない。
