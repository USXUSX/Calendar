# 探訪の共通観光地点（Calendar #254 / Frame #383）

CALが既存SQLiteの追加table `sightseeing_places` と `place_receipts` を所有する。Frameは意味APIを使う。正式Trip・旅行・Google連携は変更しない。公開情報の代表セットは `Samples/sightseeing-phase2.json`、全国拡充分は `Samples/sightseeing-phase3.json`。非公開の訪問記録を含まない。

`list_places()` / `get_place(id)` は100城と追加地点を同じ形式で返す。id 1～100は既存の城そのものを指し、`castle_id`も同番号。101以上は追加地点。弘前公園は弘前城id 4のaliasで、castle/sakura/autumnの複数分類に属する。同一地点に別IDを作らない。新しい近接地点は既存readを確認し、独立した対象なら `related_ids` に既存IDを指定する。同県の名称・alias一致または座標完全一致は重複競合として既存IDの利用を求める。近接だけを理由に自動統合しない。

共通項目:

- 位置: name / prefecture / city / longitude / latitude（WGS84）。城の位置マスターは既存値を固定し、紹介APIでは変更しない。景勝地の座標は広い地域の代表点で、入口や単木と誤解しない説明を添える。
- categories: castle / sakura / autumn。複数所属可。castle分類は既存100城専用。他分類を追加しても100名城集計に混ぜない。
- summary: 固定欄2～3行用。description: 見どころ・特徴・訪問のヒント。visited / visit_date / commentは本人の記録で、紹介から独立する。Phase 3で100城すべてに紹介を収録。画像を取得できない城はnullを許容する。
- aliases / related_ids: 同一地点の別名と別地点の関連を分ける。
- tags: label / source_url。選定や称号を推測しない。
- sources: label / url / checked_at。updated_atは紹介の更新日。
- official_url: 確認済みの公式・公的な地点案内ページ。任意項目で、未知はnull。既存の案内URLを明示して渡し、FRMは出典の並びやドメインから推測しない。代表13地点は収録済みの公式/観光協会/JNTOの案内を指定する。schema migrationは不要。
- seasons: category / typical / source_url / checked_at / annual配列。annualはyear / kind / text / source_url / checked_at。kindはactual（実績）、forecast（予想）、unannounced（確認先で未発表）、unverified（未確認）。平年情報から年別予想を作らない。2026年桜の終了済み実績が不明なら未確認とし、2027年未発表とは区別する。自動更新なし。表示は常に年を併記する。
- image: null、または代表画像の表示情報。簡単に利用できる直接画像・提供元が認める外部表示を優先し、未取得はnullのまま。法令・提供元の明確な利用制限には従い、無断コピーを前提とする収集はしない。毎回の本人確認や一律の作者・ライセンス一覧を登録条件にしない。
  - 外部表示はurl（http/https）が必須。displayはimage（省略時）または提供元が認めるembed。source_url、credit、license、license_url、conditions、captured_at、changes、checked_atは参照できるものを保持する。既存reusable=falseの画像は表示しない。既存11画像と帰属・利用条件を保持し、必要な作者・ライセンス・変更表示を省略しない。長い説明は補足へ収める。
  - 本人登録はsource=upload、CAL画像url、表示width/height、uploaded_at、source_sha256。画像実体や元のファイル名を地点JSONやGitへ埋め込まない。代表画像は常に1枚。登録画像を解除するとnullになり、以前の外部画像へ自動復帰しない。


## 正式Chat保存

既存RDCから `/usr/bin/python3 -B /Users/us/Tools/Development/Calendar_Dev/scripts/cal_places.py`。
`read` / `get --id 4` / `apply`（stdin JSON）/ `image`（本人画像、下記）/ `lookup --request-id UUID`。

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

最小Validation: `PYTHONPATH=. python3 -B -m unittest discover -s Tests -p test_places.py` と `sh Tests/castles.test.sh`。合成DBで正式CLI新規/更新/replay/lookup/競合、alias重複、100城保持、旧経路との競合を確認。Frameで375pxの共通表示を確認する。Phase 2の振り返り後、#264で全国収集と残り95城の紹介整備を実施。Phase 3の成果を本人へ返し、複数カテゴリー表示の仕様検討へは進まず停止する。

## 本人画像の正式保存（#256）

`apply_place_image_request(request)` / CLI `cal_places.py image` は登録・差替え・解除を所有する。stdin JSONはrequest_id / id / expected_revision / action（setまたはremove）。setではimage_base64（ファイル全体のBase64）を追加する。removeに画像データは渡さない。現在のgetでrevisionを取得し、応答は通常のcommitted receiptと同じlookupで照合する。

```json
{"request_id":"new-uuid","id":4,"expected_revision":"place:4:1:1","action":"remove"}
```

setのreceiptはimage_action=set、元入力のsource_sha256と、保存された表示画像urlを含む。要求のhashは元画像bytes・地点・操作・expected_revisionに基づき、同じ要求ID/同じ画像を再送しても変換を繰り返さず元receiptを返す。ID再利用の異内容と古いrevisionは競合。紹介なしの城にも登録できる。画像操作では紹介・訪問日・コメント・castlesのrevisionを変えない。

JPEG / PNG / HEIC（HEIF）/ WebP、入力12MiBまで・50百万画素まで。Mac標準 `/usr/bin/sips` で実画像を検証し、長辺1600px以内のJPEGに変換する（小さい画像を拡大しない）。表示画像からEXIF/GPS/XMP・コメントを除き、必要な向き情報と色profileだけを維持。写真ライブラリ・元ファイルは変更しない。対応外や壊れた画像・容量超過は拒否し、既存画像を保持する。Mac本番以外ではnative変換を実施済みと扱わない。

実体は既存CAL Local rootの `place-images/<表示画像SHA256>.jpg`。CALが一時書込→確定file配置→既存地点/receipt transactionで関連を保存し、commit後だけ成功を返す。FRMはDBやfileを直接書かない。`read_place_image(key)` が画像bytesを返す。keyはSHA256.jpg形式のみで、任意pathは受け付けない。DB保存失敗時も既存の関連を変えず、失敗時に未参照fileが残る場合はそのまま保持する。差替え・解除は関連の変更で、過去receiptの画像実体は削除しない。backup/切戻しでは既存DBとplace-imagesを一緒に保持する。

追加schema・本番地点の書換えは不要。両mainの公式同期後、既存Frame再起動で適用。登録画像のLocal folderは初回の本人画像保存時に作成する。本番に合成画像を登録して試験しない。外部公開先・認証を変更しない。

最小確認：`sh Tests/place-images.test.sh`（Macで実変換・縮小・向き/metadata・登録/差替え/解除・再送/lookup/競合・保存失敗・既存記録保持）、`sh Tests/places.test.sh`、`sh Tests/castles.test.sh`。Linux CIではMac標準変換だけをskipし、解除・CLI・要求検証を実行する。

## 紹介文の整理（#258）

紹介は地点固有の見どころ・歴史・特徴・重要な現地情報を簡潔に記す。「最新情報を確認して訪ねてください」「混雑状況や交通案内を確認してください」等、どの観光地にも使える定型注記や写真の一般的な注意を繰り返し付けない。「保護区画を守って観賞してください」等の一般的な行動注意も付けない。立入禁止範囲など具体的な観覧・アクセス制約、境内の段差や狭い道路、弘前城の石垣修理に伴う制限、吉野山の代表点など、その場所に必要な具体情報は保持する。FRMで文字列を削るのではなく、CALの既存description/summary自体を正式更新する。

今回の代表13地点はSamples/sightseeing-phase2.jsonのdescriptionだけを必要部分で整理し、短文は維持。公式案内リンクのためofficial_urlを追加する。出典・画像・季節・タグ・分類・位置・本人の訪問情報を変更しない。実データは各地点の最新getとrevisionで変更fieldだけをCLI applyし、committed receipt/lookupを確認する。既存の他属性が変わらないことを照合する。定期生成や自動一括収集は追加しない。

## 全国収録（Phase 3 / #264）

`Samples/sightseeing-phase3.json` は公開資料から整理した追加・更新用の内容で、本人の記録・要求ID・receiptを含めない。100城のマスターは既存値を使い、紹介済み13地点の本文は変更しない。城と同じ公園の桜・紅葉は同一IDに分類を足す。兼六園と金沢城、錦帯橋と岩国城、岡山後楽園と岡山城は別施設としてrelated_idsで関連づける。

全国セットは実地点180件（既存108＋新規72）。紹介を95城に追加し、100城すべてを紹介済みにした。桜55地点・47都道府県、紅葉56地点・44都道府県。紅葉の未収録県は静岡・島根・沖縄。複数分類に属する28地点はカテゴリー件数にそれぞれ数えるが、実地点を重複登録しない。

| 地域 | 桜 | 紅葉 |
| --- | ---: | ---: |
| 北海道 | 3 | 2 |
| 東北 | 9 | 9 |
| 関東 | 8 | 9 |
| 中部 | 10 | 9 |
| 近畿（三重を含む） | 7 | 9 |
| 中国 | 5 | 5 |
| 四国 | 4 | 5 |
| 九州・沖縄 | 9 | 8 |

位置・特徴・案内は各地点の公的／公式案内と日本城郭協会一覧を参照する。季節は案内元に加えて日本気象協会の地点別「例年の見頃」を参照し、今年の予想とは区別する。平年情報は桜53/55、紅葉47/56に収録。未確認の平年時期はseasonsへ推定値を入れず、既存の年別情報は保持、新規年別予想は追加しない。広域・高山の代表点は本文に範囲を記し、標高差のある季節を一つの確定日にしない。

画像はCommonsの提供画像を確認し、帰属・ライセンスURL・表示用縮小を保持する。地形図や別山域の写真、取得できないURLは採用しない。本人画像を含む既存画像12件を保持し、今回の設定後は148/180地点に画像あり、32地点はnull（城88/100、桜47/55、紅葉41/56。分類間重複あり）。既存13地点の画像なしも保持する。

正式投入は最新read/getを基に、地点ごとに変更fieldだけをapplyする。サンプルにimageがあっても、現在値に既存画像があればimage fieldを外す。紹介に対する本人の変更が収集後に入っていれば停止して差分を確認する。各要求は一意IDとexpected_revisionで保存し、exit 0・committed receipt・lookup・保存後getを照合する。100城の番号・位置・訪問状態・訪問日・コメント・castles revisionと既存紹介本文・画像の保持を前後比較する。DBの直接更新・自動収集・定期Job追加は行わない。

最小確認は既存places/castles testと、公開セットを合成DBへ正式CLIで適用する内容・重複・100城保持確認。公式同期後に同じCLIで本番登録し、既存Frame再起動・公開探訪画面の桜／紅葉の県別未訪問数、代表紹介・画像あり／なしを確認する。物理端末の受入は別。Phase 3終了時は成果を報告して停止する。
