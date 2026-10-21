# 探訪の共通観光地点（Calendar #254 / Frame #383）

CALが既存SQLiteの追加table `sightseeing_places` と `place_receipts` を所有する。Frameは意味APIを使う。正式Trip・旅行・Google連携は変更しない。公開情報の代表セットは `Samples/sightseeing-phase2.json`。非公開の訪問記録を含まない。

`list_places()` / `get_place(id)` は100城と追加地点を同じ形式で返す。id 1～100は既存の城そのものを指し、`castle_id`も同番号。101以上は追加地点。弘前公園は弘前城id 4のaliasで、castle/sakura/autumnの複数分類に属する。同一地点に別IDを作らない。新しい近接地点は既存readを確認し、独立した対象なら `related_ids` に既存IDを指定する。同県の名称・alias一致または座標完全一致は重複競合として既存IDの利用を求める。近接だけを理由に自動統合しない。

共通項目:

- 位置: name / prefecture / city / longitude / latitude（WGS84）。城の位置マスターは既存値を固定し、紹介APIでは変更しない。景勝地の座標は広い地域の代表点で、入口や単木と誤解しない説明を添える。
- categories: castle / sakura / autumn。複数所属可。castle分類は既存100城専用。他分類を追加しても100名城集計に混ぜない。
- summary: 固定欄2～3行用。description: 見どころ・特徴・訪問のヒント。visited / visit_date / commentは本人の記録で、紹介から独立する。未紹介の95城は紹介・画像なし。
- aliases / related_ids: 同一地点の別名と別地点の関連を分ける。
- tags: label / source_url。選定や称号を推測しない。
- sources: label / url / checked_at。updated_atは紹介の更新日。
- seasons: category / typical / source_url / checked_at / annual配列。annualはyear / kind / text / source_url / checked_at。kindはactual（実績）、forecast（予想）、unannounced（確認先で未発表）、unverified（未確認）。平年情報から年別予想を作らない。2026年桜の終了済み実績が不明なら未確認とし、2027年未発表とは区別する。自動更新なし。表示は常に年を併記する。
- image: null、またはurl / source_url / credit / license / license_url / reusable / conditions / captured_at / changes / checked_at。権利を確認できたreusable=trueのみ表示。画像と同じ位置に作者・出典・ライセンス・変更の有無を表示し、縦横比を維持する。過去の撮影日を併記し、現在の開花・復旧状況と混同しない。今回11点はCommonsの明示ライセンスによる外部縮小画像（CC BY / CC BY-SA / CC0）。永観堂・紅葉谷公園は権利確認済み画像未取得のため非表示。本人撮影写真の保存・アルバムではない。

## 正式Chat保存

既存RDCから `/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_places.py`。
`read` / `get --id 4` / `apply`（stdin JSON）/ `lookup --request-id UUID`。

```json
{"request_id":"new-uuid","id":4,"expected_revision":"place:4:1:1","values":{"summary":"更新する紹介文","updated_at":"2026-10-21"}}
```

新規idはexpected_revision=null、valuesに位置・分類・紹介・出典等の全共通項目を渡す（代表セットが形式例）。訪問記録は省略時に未訪問・日付null・コメント空。既存更新は変更fieldのみ。城の未紹介状態でも訪問fieldのみは保存できる。

`apply_place_request` はBEGIN IMMEDIATE内で要求ID・revision・内容・receiptを処理し、commit後にcommittedを返す。revisionは紹介versionと、城の場合はcastles側versionも含む。旧castle CLI/画面から更新された訪問記録とも競合を検知する。紹介だけの変更ではcastlesを更新しない。新地点の訪問は共通table内に保持。城の訪問はcastlesだけを正本として読む。
同一ID/内容の再送は元receipt。異内容はrequest_id_payload_conflict、古いrevisionはrevision_conflict。receiptは保存時item、entity_id、previous_revision、revision、request_id、receipt_idを持つ。後の現在値はgetで読む。

exit 0 + committed receiptの対象・内容一致で保存確定。競合exit 3、入力拒否exit 2、不明/storage exit 5。lookup not_found/exit 4で未実行を断定しない。不明時は同じ要求IDの照合・同内容の再送を使う。SQL・正式ファイル直接更新は禁止。

## 初回導入と本番反映

両mainの公式同期後、既存SQLiteのbackupを取り、`python3 -B scripts/migrate_places.py /Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3` を明示実行する。table追加のみ、castlesや他tableは変更しない。新規initializerは空tableを用意する。
代表セットを各地点のget結果に対応したexpected_revision（新規はnull）と一意のrequest_idで正式CLI applyへ渡す。receiptを照合し、100城の位置・状態・訪問日・コメント・revisionと68/32が導入前後で一致することを確認する。本番に試験訪問を保存しない。

既存 `com.usxusx.frame` の再起動でCAL/Frameを反映する。公開先・認証・Job・通知設定は変更しない。切戻しは画面編集を止めて旧コードへ戻し、追加地点・城の記録とreceiptは保持する。自動migration・自動収集なし。

最小Validation: `PYTHONPATH=. python3 -B -m unittest discover -s Tests -p test_places.py` と `sh Tests/castles.test.sh`。合成DBで正式CLI新規/更新/replay/lookup/競合、alias重複、100城保持、旧経路との競合を確認。Frameで375pxの共通表示を確認する。Phase 2終了後は本人が紹介・写真・表示の品質を振り返り、全国収集や残り95城への拡張はその後の判断を待つ。
