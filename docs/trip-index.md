# Chat用の旅行一覧

[chat-index / trip-index.json](https://github.com/USXUSX/Calendar/blob/chat-index/trip-index.json)は、旅行名・日程からTrip IDを探すための一覧。MacのCALが正本で、最新の旅程・現在値・revision・未処理指示はMacから取得する。通常の入口は[短い操作手順](chat-quick.md)。

## 内容と使い方

schema=cal-trip-index-v1、travels配列の各要素はid / title / dateRange（start・end、未定はnull）/ has_itinerary。初回のGit取得で短い手順と一覧をまとめて読む。手順を固定コミットで読む場合も、一覧のrefはchat-indexの現行を使う。

一覧から一意に旅行を選んだら、最初のMac実行で接続確認＋必要なreadを行う。項目索引は使わず、通常は--dateで対象日を取得する。明示ID付き依頼では既存--item-idも使える。旅行全体の文脈が必要な場合だけ全体取得する。旅程未作成の旅行基本情報はtravel-getを使う。索引にない・曖昧・Macと不一致なら、trips/travelsまたはユーザー確認で特定する。対象なしを新規作成の許可にしない。

Gitから現在値とrevisionを取得して直接保存する詳細コピー方式（#293）の評価は保留し、通常フローでは使わない。chat-data内の旅行/項目/日程/定期contextは最新branchから除去し、自動配信しない。公開済みGit履歴は書き換えない。軽量項目索引方式（#297）も効果の判断が難しいためいったん外す。item-indexの生成/配信を停止し、現行branchから除去する。

この変更は情報量と利用フローを簡素化するため。Secret・認証情報・明示非公開指定以外のツールデータは公開可能というusの方針を、秘匿優先へ戻すものではない。

## 更新と停止

既存CALの旅行関連commit後に短命のpublisherを非同期起動する。旅行一覧の内容が変わらなければGit通信は行わない。通常予定/Todoや指示だけの更新では起動しない。標準接続/RDC・Frame保存の共通commit経路を利用し、保存完了はGit通信を待たない。新しい常駐・接続・保存サービスは追加しない。

既存Calendar_Local/settings/trip-index-publisher.jsonの設定を使う。

```json
{"database":"/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3","gh":"/opt/homebrew/bin/gh"}
```

手動更新/配信失敗後の再試行は同じMacで実行する。

```sh
/usr/bin/python3 -B scripts/publish_trip_index.py --database /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3 --local-root /Users/us/Tools/LocalData/Calendar_Local
```

結果はpublished / unchanged、失敗はfailedと非0終了。settings/trip-index-publication-state.jsonへ配信状態を記録する。失敗で正式保存を取り消したり再送したりしない。次の旅行関連更新または手動実行で再試行する。停止はpublisher設定削除。すでに動作中の子processが完了する場合はある。ソースmain/GDへ運用一覧を混ぜない。
