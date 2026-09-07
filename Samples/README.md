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
