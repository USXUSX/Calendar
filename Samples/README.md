# Samples

`synthetic-trip.json` is the non-sensitive complete trip used by the read-only
prototype. It is deliberately fictional and must not be replaced with private
or production travel data.

The sample conforms to `Schemas/trip.schema.json` and is validated by
`scripts/validate_trip.py`. Its explicit `null` values and empty arrays are part
of the ChatGPT generation contract, not compatibility placeholders.

Only synthetic, non-sensitive examples that are safe to commit belong here. Real household, account, or runtime data belongs in `/Users/us/Tools/LocalData/Calendar_Local`.


## 北海道4日間の生成・受渡し代表例

`hokkaido-4days-candidate.json`はIssue #108のcomplete JSON生成例。
2027-06-12〜15、札幌3泊、小樽日帰り、新千歳空港駅発着を仮入力とした合成candidateで、usの旅行や予約データではない。Rio対象外もこの例だけの仮入力。
日付・希望順以外の交通時刻、価格、空室、食事先は創作せず未定にした。
住所・URL・座標・短い施設情報は下記の公開情報で2026-09-07に確認した。

- [JR北海道](https://www.jrhokkaido.co.jp/airport/)と[列車案内](https://www.jrhokkaido.co.jp/train/tr020_01.html)：新千歳空港・札幌・小樽を結ぶ鉄道経路。将来のダイヤは固定しない。
- [ホテル公式アクセス](https://www.jrhotels.co.jp/tower/access/)：名称、所在地、札幌駅との接続。未予約の宿泊候補。
- [小樽観光協会の運河館案内](https://otaru.gr.jp/shop/otaru-museum-canal)：名称・所在地。営業日は旅行決定後に再確認。
- [札幌観光協会の時計台案内](https://www.sapporo.travel/spot/facility/clock_tower/)：名称・住所・公式URL。
- [Wikidata Q3107971](https://www.wikidata.org/wiki/Q3107971)：大通公園の代表座標と公式URL（CC0構造化データ）。座標は小数度へ換算し、入口位置とは扱わない。

構造・semantic validationは `python3 scripts/validate_trip.py Samples/hokkaido-4days-candidate.json`。
内容確認は4連続日、3泊、日帰りの往復、予約の対象日・参照、未選択候補、未定の食事、時刻の非創作を確認する。北海道全域を短期間に詰め込まず、札幌中心部と小樽に限定した。候補選択後の市内移動・食事先等は残る未定事項である。
受渡し手順と正式採用の境界は[生成ガイド](../docs/trip-json-generation.md)を参照する。

## 新規Trip主要経路の最終確認（#126）

`hokkaido-import-review.json`は更新後のgeneration guideと現行Schemaから生成したcomplete JSON。既存の4日間例の地点・日程構造を再利用し、次の合成入力へ合わせた。実Trip・実予約ではない。

> 2027年6月12〜15日、新千歳空港駅発着で札幌に3泊。JRタワーホテル日航札幌はテスト上の予約済みとし、初日18:00に到着する予定。2日目は小樽日帰り、運河館を10:00〜11:30に訪問する確定予定。3日目は札幌で10:00〜11:00に名所を訪ねたいが、時計台・大通公園は候補のまま。食事と鉄道時刻は未定。空港から札幌への移動は重要、運河館往復の徒歩は通常コネクタ。帰りの指定席は予約予定で未予約。Rioは対象外。

booked、日付、訪問時刻はこの入力で与えた仮の事実。交通ダイヤ・営業日・価格・空室を保証しない。確定予定・時刻・予約状態は独立して表現し、移動をScheduleItemへ複製しない。候補は未選択のまま保存する。

2026-09-10に確認した公開情報:

- [ホテル公式アクセス](https://www.jrhotels.co.jp/tower/access/): 名称・住所・札幌駅直結。
- [小樽観光協会の運河館案内](https://otaru.gr.jp/shop/otaru-museum-canal): 名称・住所・公式市サイトへのリンク。
- [時計台公式](https://sapporoshi-tokeidai.jp/): 名称・住所・公式URL。
- [大通公園公式](https://odori-park.jp/)と[Wikidata Q3107971](https://www.wikidata.org/wiki/Q3107971): 名称・公式URL・CC0代表座標。入口の座標ではない。
- [JR北海道](https://www.jrhokkaido.co.jp/airport/): 新千歳空港・札幌・小樽の経路。将来の列車時刻は未定。

上記で確認できない住所・座標・評価はnull。Schema / semantic検証と一時取込後の正式採用・直接編集は `sh Tests/trip-json-import.test.sh`。Frameの読込・内容確認・取込・通常表示・編集はこの同じJSONを一時環境で使う。
