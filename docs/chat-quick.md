# CALの通常操作

Gitは手順と[旅行一覧](https://github.com/USXUSX/Calendar/blob/chat-index/trip-index.json)（path=trip-index.json、ref=chat-index）を取得するために使う。現在値・revision・未処理指示はMacの専用CLIから必要な範囲だけ取得する。通常操作のためにソース・TDS・Issue・手順全文を探索し直さない。

## 取得 → 判断 → 保存

1. 保存までの処理時間を毎回回答に表示する。最初のツール呼出し冒頭で呼出元の開始時刻と経過時間用の時計を保持し、その後に手順/一覧を取得する。同じ持続する呼出元の時計を使い、時計取得だけのMac往復は追加しない。
2. 旅行名・日程からTrip IDを選ぶ。複数一致は推測せず確認する。一覧にない/古い場合だけMacのtrips/travelsで確認する。通常予定/Todoは旅行の旅程と分ける。
3. 対象MacはusMac-miniM4Pro.local。接続済みMacの標準実行を優先し、利用できなければ既存RDCを使う。Cloud shellでMacのCLIを探さない。接続確認と下表の取得を一つの実行にまとめる。
4. Git取得・Mac取得・保存の呼出し直前と応答直後を同じ呼出元時計で保持する（可能な範囲だけ。計測用の追加呼出しはしない）。返った現在値と未処理指示を読み、対象項目を選んで変更するfieldだけを準備する。同じ応答のrevisionを使い、次のMac実行で正式保存する。
5. 保存応答を受け取った直後に同じ呼出元時計の終了時刻を保持する。完全なstatus=committedとreceiptの要求ID・対象・操作・変更内容・revisionが今回の要求に対応することを確認し、保存完了と「保存までの処理時間：XX.XXX秒」を先に報告する。exit 0の回収は待たず、後続確認へ分離する。受付・途中出力・欠落したreceipt・競合は保存成功としない。

| 分かっている範囲 | 取得 |
| --- | --- |
| Trip IDと項目ID | trip-get --id <Trip ID> --item-id <項目ID> |
| 通常の入口：Trip IDと日付 | trip-get --id <Trip ID> --date YYYY-MM-DD |
| 旅行全体の前後関係が必要 | trip-get --id <Trip ID> |
| 通常予定/Todo | read --start YYYY-MM-DD --end YYYY-MM-DD。既知IDはget --kind event またはtodo --id <ID> |

項目索引は取得しない。通常は日付限定取得から日時・名称で対象を選び、判明した項目IDを保存要求と後続照合に使う。依頼で項目IDが明示されている場合の既存--item-id機能は保持する。

日付限定はその日のday（予定を含む）・transports・関連places/bookingsと、全未処理instructions・Trip全体revisionを返す。項目限定と日付限定はcomplete Tripではないので全体saveへ渡さない。--dateと--item-idは併用しない。日付不在/不正/曖昧は拒否され、全文を自動取得しない。必要な文脈が足りなければ取得範囲を広げる。

処理時間は手順取得・接続確認・対象取得・変更準備・保存確定receipt受信までを含み、報告文の作成・終了確認・後続照合は含めない。開始/終了時刻（JST）も同じ時計から示す。呼出元で時刻を保持できない場合は「処理時間：計測不可」とし、Macのcommitted_atや異なる時計で補わない。失敗・競合・未保存では成功所要時間を表示せず、その状態を報告する。

## 最初のMac実行

以下の最後のCLI行を上表から一つ選んで実行する。仮のTrip ID/日付は実値へ置き換える。標準接続なら1つのexec_command、RDCなら1つのstart_processへブロック全体を渡し、確認だけで呼出しを終えない。

```sh
set -e
cd /Users/us/Tools/Development/Calendar_Dev
/usr/bin/python3 -B - <<'CAL_CONNECTION_CHECK'
import json, socket
from pathlib import Path
root = Path('/Users/us/Tools/Development/Calendar_Dev')
if socket.gethostname().split('.')[0].casefold() != 'usmac-minim4pro':
    raise SystemExit('Unexpected Mac')
if Path.cwd().resolve() != root.resolve() or not (root/'scripts/cal_schedule.py').is_file():
    raise SystemExit('CAL checkout or CLI unavailable')
print(json.dumps({'host':socket.gethostname(),'cwd':str(Path.cwd())}))
CAL_CONNECTION_CHECK
/usr/bin/python3 -B scripts/cal_schedule.py trip-get --id '対象Trip ID' --date 'YYYY-MM-DD'
```

## 次のMac実行：保存

項目の名称変更はtrip-operationのstdinへ次の形式を送る。仮値は使わず、今回のMac取得値から作る。source_typeはscheduleItemまたはtransport、source_item_idは対象のstable ID。名称はchanges.title（ScheduleItem.actionに対応）で、Place.nameは変えない。

```sh
cd /Users/us/Tools/Development/Calendar_Dev
/usr/bin/python3 -B scripts/cal_schedule.py trip-operation <<'CAL_REQUEST'
{"request_id":"新しい要求ID","trip_id":"取得したTrip ID","operation":"item","expected_revision":{"trip_version":1,"effective_hash":"取得値","instructions_hash":"取得値"},"values":{"source_type":"scheduleItem","source_item_id":"取得した項目ID","changes":{"title":"変更後の名称"}}}
CAL_REQUEST
```

時刻・コメント等の意味fieldは[局所変更契約](direct-schedule.md#chatからの局所変更)、通常予定/Todoは[正式更新](chat-schedule.md#正式更新)を必要な場合だけ読む。新規/全体再構成・地点追加は[全体保存](chat-schedule.md#旅程の正式更新205)と生成/座標補完の契約を使う。全体readやJSON再生成を局所変更へ常に要求しない。

## 結果回収・後続確認

完全な保存確定receiptを先に受け取れた場合、session/PIDが残っていても報告を待たない。報告後も同じturnで同じハンドルの最終出力・終了コードを回収し、lookupと再取得を続ける。保存確定receiptをまだ受け取れていない受付/途中出力/timeoutは結果不明として回収・照合を先に行う。再接続しても要求ID/内容を保持する。

revision_conflict（exit 3）は保存拒否。同じ応答のcurrentで最新内容を確認し直し、再判断した操作には新しい要求IDを使う。current_unavailableなら追加readする。無条件上書きしない。

応答不明は同じ要求IDをlookupし、同じ内容だけ再送する。同じID/内容は元receiptを返し、異なる内容は拒否される。not_foundだけで未実行と断定しない。

保存完了報告後、[時間ログ](chat-timing.md)を記録し、lookupと対象再取得をまとめて照合する。ログは既存の照合用Mac実行の先頭で /usr/bin/python3 -B scripts/record_chat_timing.py のstdinへ呼出元の開始/保存受信時刻・観測済み呼出し時刻・経路・操作種別・要求ID/receipt IDをJSONで渡す。記録のためだけの往復は追加せず、ログ失敗でも照合を続ける。対象項目IDが分かった後は--item-idで取得する。receipt/revision・変更値・保持fieldを確認する。全て正常なら追加メッセージ・正常一覧・「後続チェック完了」の追記は出さない。ログ記録失敗・不一致・非0終了・確認不能など問題がある場合だけ、保存済みの事実と区別して問題と必要な対応を追加報告する。画面/API/実機の確認は要求された場合だけ行う。[詳細契約](chat-schedule.md)は必要時だけ参照する。
