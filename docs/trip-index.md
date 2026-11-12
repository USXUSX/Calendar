# Chat用公開旅行索引（#291）

usの明示承諾により、公開GitHubの [chat-index / trip-index.json](https://github.com/USXUSX/Calendar/blob/chat-index/trip-index.json) に旅行名・日程・IDと旅程有無だけを掲載する。通常データの非公開配置原則に対する、この索引だけの例外。旅程本文・項目名・地点・住所・予約・参加者・メール・指示・revision・credentialは含めない。通常予定やTodoの索引ではない。

## Chatで使う

通常操作の手順を取得するときに、このファイルをまとめて取得する。GitHub fetch_fileなら repository_full_name=USXUSX/Calendar、path=trip-index.json、ref=chat-index。手順書を過去コミットへ固定した場合も、索引のrefにはchat-indexを使う。

schemaはcal-trip-index-v1、travelsはid / title / dateRange（start・end、未定はnull）/ has_itineraryの配列。旅行名・依頼の日付からChatが旅行を選ぶ。一意に特定できればMacへの一覧取得は不要。has_itinerary=trueなら接続確認とtrip-get --idを一つの実行で行い、その最新旅程から項目を選ぶ。項目IDも既知の場合だけ--item-idを使う。has_itinerary=falseはtravel-getへ進む。新規旅程は既存の旅行先行管理・作成契約に従う。

索引は検索のヒントであり、現在値・revision・正式保存の根拠ではない。Mac取得結果の旅行名・日程・対象項目を依頼と照合し、最新版revisionを保存へ渡す。索引が取得不能・対象なし・複数一致・Macと不一致の場合は、既存travels/tripsによる探索またはユーザー確認に戻る。候補がないことを新規作成の許可としない。非同期更新なので直前の変更が未掲載の場合がある。

旅行を索引から選べる通常の局所変更は、「接続確認＋最新旅程取得」「AI判断後の正式保存」の基本2回のMac実行となる。Git取得・接続先探索・出力/終了コードの回収・後続チェックまで2往復に収まる保証ではない。実際の速度効果は別途確認する。

## 更新と運用

コードmainとは別のデータbranch chat-indexを使う。索引の更新はmainへmergeせず、Calendar_GDへ同期しない。CALの共通commit経路は、trips / travel_basics / direct_overridesの変更後、設定がある場合だけ短命のpublisher子processを起動する。Chatの標準接続/RDCとFrameのブラウザ操作の双方を含む。新しい常駐・スケジュール・サービスは追加しない。

子processは排他lock取得後、専用domain APIの最新旅行一覧から許可fieldだけを作り、前回成功時と同じならネットワーク通信をしない。変更時だけ既存gh認証でGitHub Contents APIへ反映する。正式保存はGit通信を待たない。失敗しても保存receiptやGoogle同期結果を変更せず、次の旅行関連commitまたは手動実行で再試行する。外部失敗だけを理由に正式保存を再送しない。

MacのCalendar_Local/settings/trip-index-publisher.jsonを明示設定する。例は配置説明用であり、testから実設定や実GitHubへ送信しない。

```json
{"database":"/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3","gh":"/opt/homebrew/bin/gh"}
```

初回だけchat-index branchをmainの既知コミットから作り、上記設定を置いて、同じMacで次を実行する。GitHub認証は既存ghのものを使い、Secretを設定ファイルやコードへコピーしない。

```sh
/usr/bin/python3 -B scripts/publish_trip_index.py --database /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3 --local-root /Users/us/Tools/LocalData/Calendar_Local
```

結果はpublished / unchanged、失敗はfailedと非0終了。settings/trip-index-publication-state.jsonで配信状態を確認する。子processの失敗は保存応答へ混ぜない。Frame等の長時間processはコード反映時に既存の再起動手順で新しいdomainを読み込ませる。

停止はtrip-index-publisher.jsonの削除で行い、必要ならGitHubの索引も削除する。既に公開されたGit履歴は残る。設定削除は未起動の更新を停止し、既に動作中の子processまで取り消すものではない。
