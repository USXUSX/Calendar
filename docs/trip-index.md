# Git参照コピーによるChat更新（#293）

Mac上のCAL SQLite＋正式Trip JSONを唯一の正本とする。Gitのchat-index branchはChatの対象特定・変更準備用の参照コピー。コピーから取得した対象ID・現在値・revisionで要求を組み立て、最初のMac実行で接続確認と正式保存を続けて行う。毎回Macから事前取得することを保存条件にしない。

usはSecret・認証情報・明示非公開指定を除くツール情報の公開を許可している。金融情報も含む一般方針であり、CALの旅行名だけの例外ではない。本機能はCALの旅行/旅程・通常予定/Todo・定期条件/例外・未処理指示とrevisionを既存公開Gitへ配信する。DBそのもの、設定、credential、receipt履歴は配信しない。

## Gitのファイル

repository_full_name=USXUSX/Calendar。最初に手順書と [trip-index.json](https://github.com/USXUSX/Calendar/blob/chat-index/trip-index.json)（ref=chat-index）をまとめて取得する。手順書を過去コミットへ固定した場合も、コピーはchat-indexの現行を読む。

| ファイル | 内容・用途 |
| --- | --- |
| trip-index.json | schema=cal-chat-copy-v2。travelsに旅行名・期間・ID・旅程有無と各参照path。schedule_pathも持つ |
| 各旅行のitems_path | context_scope=items。全項目のstable ID・種別・日付・現在値、地点名、全未処理instructions、Trip全体revision。名称・時刻・コメントなどの局所更新用 |
| 各旅行のcontext_path | effective complete Trip＋instructions＋revision。前後関係・地点詳細・旅程全体の検討用。必要な場合だけ読む |
| 各旅行のtravel_path | 旅行基本情報とそのrevision。旅程未作成の旅行も含む |
| schedule_path | 単発Event/Todoのget相当context（現在行＋revision）と、定期seriesの条件・期間別テンプレート・例外・revision |

一覧から一意に選んだ旅行/日程だけを読む。旅行名だけで複数一致したら日付等と照合し、曖昧なまま保存しない。items_pathのitemは元のScheduleItem/Transportの値であり、CLIのchangesは所有契約の意味field名を使う（例: ScheduleItem.actionの名称変更はchanges.title）。

items_pathはcomplete Tripではない。全体saveやtrip-resolveへ渡さない。全体編集はcontext_pathのtripを基に行い、座標補完等の既存契約を維持する。別コピーの現在値とrevisionを混ぜず、変更を準備したcontext自身のrevisionを使う。複数ファイルを一緒に判断する場合は同じrevision/commitであることを確認する。

定期の各回IDは既存のrec:<series UUID>:<元の発生日>、expected_revisionはseriesのrevision。条件・例外から対象を確実に特定できない場合は既存read/getを使う。無限の各回をGitへ全展開しない。

## 更新フロー

1. Gitから手順・索引・必要なcontextを取得し、対象と変更内容を判断する。未処理指示も読む。
2. 要求IDと送信内容を保持する。変更するfieldだけを送り、同じcontextのrevisionをexpected_revisionへそのまま入れる。
3. 最初のMac実行で対象Mac/checkout/CLIの確認と専用CLIの正式保存を続けて行う。確認だけの往復、同じ対象の事前getを追加しない。標準接続とRDCの両方で使う。
4. CALが正本のrevisionと照合し、一致時だけ既存transaction・receipt契約で保存する。exit 0・committed・要求内容の一致を確認して保存完了を先に報告し、その後lookup・再取得を行う。

コピーが取得不能・対象がない・情報不足の場合は既存Mac readを使う。対象がないことを新規作成の許可としない。Gitコピーを編集してもCAL保存にはならない。

## コピーが古いとき

CLIは従来どおりexit 3 / rejected / reason=revision_conflictで保存を拒否する。その同じ応答にcurrentとして最新contextを付ける。局所Tripは対象項目のcontext、項目削除等で絞れなければ完全contextを返す。通常Event/Todo、旅行基本情報、定期series/回も対応する。最新値を取れなければcurrent_unavailable=trueとなり、既存readへ戻る。

currentは拒否後の取得時点の値であり、保存済みや次の保存の予約ではない。AIが依頼と最新内容を照合し直し、必要な変更だけを新しい要求ID・そのrevisionで再送する。自動rebase・無条件上書きはしない。同じ要求IDの別payload拒否はcurrentを付けず、元のlookup/replay契約を維持する。

## 更新と運用

既存のpublisher設定と短命の子processを利用する。旅行・旅程・通常予定/Todo・定期・指示の共通commit後に非同期で更新し、正式保存はGit通信を待たない。Mac内で一つの読取状態から必要な参照ファイルを作り、Git Trees/Commit/ref APIで一つのcommitにして非force更新する。正式Tripの中断処理が残っている間は公開を見送り、既存の回復手順を使う。コピー作成のために中断状態を修復しない。

内容が前回の成功時と同じなら通信しない。配信失敗はsettings/trip-index-publication-state.jsonへ記録し、次の正式変更または手動publisher実行で再試行する。外部失敗だけを理由に正式保存を再送しない。source mainやCalendar_GDへ運用コピーを混ぜない。新しい常駐・接続・保存サービスは追加しない。

MacのCalendar_Local/settings/trip-index-publisher.jsonは既存設定を使用する。

```json
{"database":"/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3","gh":"/opt/homebrew/bin/gh"}
```

手動配信・失敗後の再試行:

```sh
/usr/bin/python3 -B scripts/publish_trip_index.py --database /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3 --local-root /Users/us/Tools/LocalData/Calendar_Local
```

結果はpublished / unchanged、失敗はfailedと非0終了。Frame等の長時間processはコード反映時に既存手順で再起動して共通commit hookを読み込ませる。停止はpublisher設定の削除。既に起動中の子processは完了する場合があり、公開済みGit履歴は残る。

Mac実行が基本1回になるのは、Gitで変更準備が完了しrevisionが一致する操作。Git取得、接続先探索、出力/終了コード回収、後続チェックまで含めて全て1往復になるという意味ではない。全体の短縮効果は新規Chatの通常依頼で別途判断する。
