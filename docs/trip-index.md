# Chat用の旅行一覧と項目索引

[chat-index / trip-index.json](https://github.com/USXUSX/Calendar/blob/chat-index/trip-index.json)は、旅行名・日程からTrip IDを探すための一覧。MacのCALが正本で、最新の旅程・現在値・revision・未処理指示はMacから取得する。通常の入口は[短い操作手順](chat-quick.md)。

## 内容と使い方

schema=cal-trip-index-v1、travels配列の各要素はid / title / dateRange（start・end、未定はnull）/ has_itinerary。初回のGit取得で短い手順と一覧をまとめて読む。手順を固定コミットで読む場合も、一覧のrefはchat-indexの現行を使う。

一覧から一意に旅行を選んだら、最初のMac実行で接続確認＋必要なreadを行う。項目単位の依頼でIDが不明な場合だけ、下記の軽量索引から候補IDを選ぶ。ID既知なら索引を再取得しない。日全体の依頼は索引を読まず--date、旅行全体の文脈が必要な場合だけ全体取得する。旅程未作成の旅行基本情報はtravel-getを使う。索引にない・曖昧・Macと不一致なら、trips/travelsまたはユーザー確認で特定する。対象なしを新規作成の許可にしない。

Gitから現在値とrevisionを取得して直接保存する詳細コピー方式（#293）の評価は保留し、通常フローでは使わない。chat-data内の旅行/項目/日程/定期contextは最新branchから除去し、自動配信しない。公開済みGit履歴は書き換えない。軽量項目索引は詳細コピーとは別の検索用投影で、Mac取得を省略しない。

この変更は情報量と利用フローを簡素化するため。Secret・認証情報・明示非公開指定以外のツールデータは公開可能というusの方針を、秘匿優先へ戻すものではない。

## 項目単位の依頼だけで使う軽量索引（#297）

同じchat-indexブランチに次の2種類を置く。schemaはcal-item-index-v1。旅行一覧の形式は変更しない。

| path | 内容・用途 |
| --- | --- |
| item-index/by-date/YYYY-MM-DD.json | date / trips配列（trip_id / items）。依頼の日付が既知なら手順・旅行一覧とまとめて取得し、正しいTrip内で対象を選ぶ |
| item-index/by-trip/Trip-ID.json | trip_id / days配列（date / items）。日付が不明な項目依頼では旅行を選んでから取得 |

itemsの各要素はsource_type（scheduleItem / transport）・source_item_id・start（未定はnull）・titleのみ。transportのtitleは移動種別と発着地点名。詳細コメント・予約・座標・未処理指示・revisionは載せない。両ビューは同じMac状態から作り、一つのGit commitで更新し、消えた日付/旅行の索引は削除する。

依頼の範囲判断と同時に索引の要否を決め、別の判定往復を増やさない。日全体の取得には項目索引を追加しない。索引の候補IDからMacのtrip-get --item-idを行い、最新名称・日付・時刻・revision・指示を確認して変更要求を作る。索引なし、複数一致、古いID、Mac結果との不一致なら日付限定等の既存readへ戻す。対象を推測せず、保存は常にMac取得revisionで照合する。

検索量と取得後のAI処理量を減らす仮説であり、速度改善は未計測。通常チャットの新規チャットから同じ条件で評価し、保存後チェックは計測に含めない。

## 更新と停止

既存CALの旅行関連commit後に短命のpublisherを非同期起動する。旅行一覧・項目索引の内容が変わらなければGit通信は行わない。通常予定/Todoや指示だけの更新では起動しない。標準接続/RDC・Frame保存の共通commit経路を利用し、保存完了はGit通信を待たない。新しい常駐・接続・保存サービスは追加しない。

既存Calendar_Local/settings/trip-index-publisher.jsonの設定を使う。

```json
{"database":"/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3","gh":"/opt/homebrew/bin/gh"}
```

手動更新/配信失敗後の再試行は同じMacで実行する。

```sh
/usr/bin/python3 -B scripts/publish_trip_index.py --database /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3 --local-root /Users/us/Tools/LocalData/Calendar_Local
```

結果はpublished / unchanged、失敗はfailedと非0終了。settings/trip-index-publication-state.jsonへ配信状態を記録する。失敗で正式保存を取り消したり再送したりしない。次の旅行関連更新または手動実行で再試行する。停止はpublisher設定削除。すでに動作中の子processが完了する場合はある。ソースmain/GDへ運用一覧を混ぜない。
