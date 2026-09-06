# 共通施設取得とPlace補完（Issue #90）

Goal 1の②③⑤⑥向けに`Sources/place_acquisition.py`の`FacilityAdapter.search(FacilityQuery)`を共用する。
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
候補なしは`no_candidates`になる。説明等の根拠は将来の⑤で同じadapterから使えるが、コメントへ自動転載しない。

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
prepared = calendar.prepare_place_enrichment(
    trip_id, {"place_id": place_id}, result, 0, confirmed=True)
```

対象は`{"place_id": ...}`または`{"temporary_id": ...}`のいずれか。
CALがそのTripへの帰属、Working temporary itemの非空place_nameを確認し、名称・既知住所を取り出す。
対象identityは外部へ渡さず、結果にCAL側で結び付ける。areaはcallerが対象日の代表エリアを渡す任意hint。
provider固有IDはadapter内に留め、CAL結果へ返さない。
結果の`candidates[].fields`と表示用の出典・取得時刻等の`context`は分離し、CALがfield名、型、有限の座標範囲、HTTPS URLを再検証する。

一件でも施設identityの明示確認が必要。`prepare_place_enrichment`へは内部callerが保持した未変更の
取得結果を渡し、UIからは候補indexと確認だけを受け取る。任意のUI JSONやprovider応答を直接この入力にしない。
選択時にTrip・対象一致と現行入力を再確認し、入力が変わっていればConflictにする。
返す`fields`は空のaddress/location/urlsだけで、既存の非空値は追記も置換もしない。
補完がなければ`unfilled`となる。provider ID、根拠本文、保存制限値はこのpayloadに含まない。

これは既存Step 8どおり**補完候補の準備まで**で、独立した正式採用commandやUIを新設しない。
採用callerは明示確認済みの`fields`だけを同じstable Placeの完全Trip候補に適用し、既存の
`adopt_working_trip_candidate`によるSchema・参照・Working stale検証とatomic adoptionを使う。
temporary itemは完全Trip生成時のstable Placeへ収束させる。Workingへ地点fieldや別の正本を追加しない。
他の予定への自動変更は行わない。関連testでsynthetic Tripの取得→選択→完全Trip採用と他field不変を確認する。

## 公式資料の確認

2026-09-06確認。保存方針の根拠とAPI仕様：

- [Wikidata Data access](https://www.wikidata.org/wiki/Wikidata:Data_access): 構造化データCC0、出典表示は推奨、アクセス方法と取得制限。
- [Wikibase API](https://www.mediawiki.org/wiki/Wikibase/API): wbsearchentities / wbgetentities。
- [API Etiquette](https://www.mediawiki.org/wiki/API:Etiquette): 直列request、maxlag、負荷・失敗時の対応。
- [User-Agent policy](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy): アプリ名と連絡可能な識別子。

通常Validationはmock transportと一時DBのみで、課金・Secret・Calendar_Localへのアクセスを必要としない。
