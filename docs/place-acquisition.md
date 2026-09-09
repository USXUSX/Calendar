# 共通施設取得とPlace補完（Issue #90）

Place同定・事実補完向けに`Sources/place_acquisition.py`の`FacilityAdapter.search(FacilityQuery)`を共用する。
Queryは名称・代表エリア・既知住所だけで、Trip、参加者、予約、コメント、CAL identityを受け取らない。
②③⑤の機能・UI、天気、OpenAI、実運用設定はこの実装に含まない。

## 取得adapter

`WikidataAdapter`は認証・API有効化・課金設定なしの公開read APIを使う。
名称のlabel/alias検索を最大5件に制限し、続く1回のまとめ取得で名称、住所P6375、地球座標P625、公式URL P856を解釈する。
地域・住所は照合用hintとし、検索順位や名前の一致だけで施設同定を完了させない。
地域文字列の部分一致は参考表示だけで、支店を自動選択する根拠ではない。
取得本文やリンク先の指示を実行せず、公式URLのリンク先も自動取得しない。

1操作最大2回の直列request、各10秒timeout（設定上限30秒）、request間隔1秒、2 MB応答上限、
maxlag=5、識別可能なUser-Agent、gzipを使用する。自動retryはなく、429/503のRetry-After
（最低60秒）、API error後60秒は同じadapterで再送しない。対話callerはadapterを再利用し、
新しいinstanceや並列呼出しで制限を回避しない。常駐サービス、永続cache、取得履歴は作らない。

`FacilityCandidate.persistable`はadapterが保存を認めたfieldだけ。
`temporary`は出典、取得時刻、provider ID、説明、利用・表示条件と有効期限を含む操作中だけの情報。
他providerの追加時は保存許諾が確認できるfieldだけを前者へ入れ、保存不明・禁止の値は後者に置く。
候補選択でこの区別を解除しない。取得失敗は本文・例外・照会内容を含まない`unavailable`、
候補なしは`no_candidates`になる。

Wikidata adapterのpersistableはCC0構造化値だけ。deprecated、qualifier付き、同順位で複数値の
statementは採用しない。地球以外の座標、不正値、非HTTPS URLは未補完にする。
名前以外のfieldがない候補も許容する。名称は候補照合と後続の新規追加に使え、既存名称の置換には使わない。
Wikidata以外のページ本文・画像・公式サイト内容の保存権限をCC0から推定しない。

## CAL semantic境界

```python
from Sources.place_acquisition import WikidataAdapter

adapter = WikidataAdapter()  # callerが再利用
result = calendar.get_place_enrichment(
    trip_id, {"place_id": place_id}, adapter, area="東京")
# 一件でもconfirmation_required。複数件はambiguous。取得・確認は書き込まない。
adopted = calendar.adopt_place_enrichment(
    "enrich-command", trip_id, place_id, result, 0, confirmed=True)
```

対象は`{"place_id": ...}`または`{"temporary_id": ...}`のいずれか。
CALがそのTripへの帰属、Working temporary itemの非空place_nameを確認し、名称・既知住所を取り出す。
対象identityは外部へ渡さず、結果にCAL側で結び付ける。areaはcallerが対象日の代表エリアを渡す任意hint。
provider固有IDはadapter内に留め、CAL結果へ返さない。
結果の`candidates[].fields`と表示用の出典・取得時刻等の`context`は分離し、CALがfield名、型、有限の座標範囲、HTTPS URLを再検証する。

一件でも施設identityの明示確認が必要。採用・候補準備commandへは内部callerが保持した未変更の
取得結果を渡し、UIからは候補indexと確認だけを受け取る。任意のUI JSONやprovider応答を直接この入力にしない。
選択時にTrip・対象一致と現行入力を再確認し、入力が変わっていればConflictにする。
返す`fields`は空のaddress/location/urlsだけで、既存の非空値は追記も置換もしない。
補完がなければ`unfilled`となる。provider ID、根拠本文、保存制限値はこのpayloadに含まない。

stable PlaceのGoal 1通常経路は`adopt_place_enrichment(command_id, trip_id, place_id, result,
candidate_index, confirmed=True)`とする。CAL内で候補準備・型・Schema・参照を再検証し、
対象の不足address/location/urlsだけを同一transactionでDirect Overrideへ保存する。
現在の正式な表示値はBaselineどおりeffective Tripから再表示する。Trip JSON本体へのコピーや
callerによる完全Trip構築、Workingの新規作成・更新・削除は行わない。
戻り値はstatus（adopted / unfilled）、trip_id、target、updated_fields、trip、view。
未補完なら書込みはなく、既存の非空値、他Place・他予定・他Trip、他のDirect Overrideを維持する。
確認と不足値検証の前にSQLiteの書込みlockを取り、途中失敗は全補完fieldをrollbackする。
未完了のTrip採用journalがある場合はConflictとし、このcommandからrecoveryを呼ばない。

既存Workingがあっても保存row・生成stateを一切変更しない。effective Tripが変わるため、
既存Workingのstale表示は従来のrevision比較によってtrueになる。自動rebaseはしない。
temporary itemは`prepare_place_enrichment`による候補準備までを維持し、stable Place用の
正式採用commandへ渡せない。将来の完全Trip生成時にstable Placeへ収束する境界は維持する。
UI、実運用設定、②③⑤⑦の機能は本Issueに追加しない。

## 公式資料の確認

2026-09-06確認。保存方針の根拠とAPI仕様：

- [Wikidata Data access](https://www.wikidata.org/wiki/Wikidata:Data_access): 構造化データCC0、出典表示は推奨、アクセス方法と取得制限。
- [Wikibase API](https://www.mediawiki.org/wiki/Wikibase/API): wbsearchentities / wbgetentities。
- [API Etiquette](https://www.mediawiki.org/wiki/API:Etiquette): 直列request、maxlag、負荷・失敗時の対応。
- [User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy): アプリ名と連絡可能な識別子。

通常Validationはmock transportと一時DBのみで、課金・Secret・Calendar_Localへのアクセスを必要としない。

Issue #93の`include_comment_evidence=True`では追加の根拠取得を最大1回許可する。通常取得の既存上限・Place採用契約は変えない。詳細は[コメント追記](comment-enrichment.md)を参照する。

## Issue #116: 正式Place全般を対象にする

`place_id`はeffective Tripのplacesで解決する。selection済み、未選択candidatePlaceIds、
未定/暫定の候補予定に含まれるPlaceを区別しない。Direct Override追加PlaceやChat candidateの
正式採用後も同じ境界を使う。補完はPlaceの不足値だけを更新し、candidatePlaceIds、selection、
予定内容、Workingは変更しない。Frameでは各予定の補完操作から選択済み・候補Placeを選べる。
CAL内検索/AFM推薦とコメントAIは廃止した。Working保存基盤の移行・削除は行わない。

#116では確認済み公式URLを任意Place.officialUrlとして区別する。Wikidata P856はurlsとofficialUrlへ返す。既存の施設確認と不足値採用を使い、非空officialUrlは上書きしない。新規Placeのlookup結果も同じfieldを保存できる。
