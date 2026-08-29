# ChatGPT向けTrip JSON生成ガイド

> **Status:** Issue #46以降も、AIがformalな完全Trip JSONを生成・再生成する基本方式として維持する。再構築後は現在のTrip JSONに`AI Instructions`と`Direct Overrides`を加えて次版を生成する。入力の保存形式と統合手順は後続Issueで定める。

## 入力として渡すもの

ChatGPTへ次を同時に渡す。

1. `Schemas/trip.schema.json`の全文
2. 旅行の事実、未確定事項、変更指示
3. 既存旅行の更新では現在の完全JSON

## 生成指示

次の指示を使う。

> Calendarの正式スキーマに一致する完全な旅行JSONを1個だけ生成してください。Markdownや説明文は付けません。旧形式を残さず、不足値はスキーマ指定の`null`または空配列にします。IDは英数字・ハイフン・アンダースコアだけを使い、既存対象のIDは維持します。行動、時刻、場所、経路を別フィールドにし、同じ説明を複数フィールドへ重複させません。分からない事実は推測せず未確定として表現します。

## 重複を避ける規則

- `Day.title`には日付ではなく、その日の短いテーマを書く。
- `Day.routeSummary`には主な経路だけを書く。
- `ScheduleItem.action`には「昼食をとる」「美術館を見る」等の行動を書く。時刻やPlace名を埋め込まない。
- `summary`は一覧で必要な短い補足、`details`は追加事実だけにする。同じ文を両方へ書かない。
- 移動はScheduleItemへ複製せず、Transportだけにする。
- Placeは1地点1件とし、ScheduleItem、Transport、BookingからID参照する。
- Bookingの`notes`には予約条件等の正式情報だけを入れ、ChatGPTへの変更指示は入れない。

## 検証と表示

生成物を説明文から切り離したUTF-8 JSONファイルとして一時作業場所へ保存する。検証前のJSONは`Calendar_Local/trips/`へ置かない。不正な1件が旅行一覧の読み込みも止めるためである。

次を実行する。

```sh
python3 scripts/validate_trip.py /path/to/generated-trip.json
```

エラーがあれば該当パスとエラーだけをChatGPTへ返し、部分パッチではなく同じ完全JSONを修正させる。検証成功後に、ファイル名を`id`と一致させて`Calendar_Local/trips/<trip-id>.json`へ配置し、Calendarの一覧、旅程、地図、準備、コメントを確認する。Calendar側で欠損値の補完や旧形式変換は行わない。

## 既存旅行の修正

現在の完全JSON、変更依頼、正式SchemaをChatGPTへ渡す。次の指示を追加する。

> 指定した変更だけを反映した次版の完全JSONを生成してください。同じ対象の既存IDは維持し、変更対象外の事実、配列順、参照関係を変えません。出力はJSON 1個だけにしてください。

生成後は新規作成と同じvalidatorを実行する。検証成功だけで採用せず、変更対象の値、主要ID、項目件数、Calendar表示を確認してから現在ファイルを置き換える。

## 問題の切り分け

- validatorが失敗する: 生成JSONまたはSchema契約の問題。エラーパスをChatGPTへ返す。
- validatorは成功するがサーバーが拒否する: ファイル名と`id`、UTF-8、配置場所を確認する。
- サーバーは返すが表示できない: Calendar UIの問題として、consoleと該当画面を確認する。
- 表示できるが内容が意図と違う: 旅行資料または生成指示の問題。UIで推測・補正しない。

## 確認済みの基本フロー

Issue #40では、旅行計画資料からの新規完全JSON生成、参照漏れエラーを使った再生成、既存IDを維持した内容変更、再検証、一覧と5画面の表示までを確認した。新機能、自動修正、自動同期は必要なく、`生成 → 検証 → 配置 → 表示確認`を基本運用とする。

## 実旅行での内容確認

Schema成功は、JSONの構造と参照が正しいことを示すが、旅行内容の重複や不足までは保証しない。実旅行では表示前後に次も確認する。

- 日付だけの`Day.title`を使わず、その日のテーマが読めること。
- 同じ移動をScheduleItemとTransportへ二重に持たず、移動はTransportだけにすること。
- 同じ食事や宿泊を別ScheduleItemへ重複させないこと。
- 同じ場所を複数Place IDで定義せず、既存IDへ参照を統合すること。
- ScheduleItemを統合・削除するとき、候補Placeを先に残す項目へ統合し、候補情報を落とさないこと。
- 参照されないPlaceを残さないこと。
- Bookingを対象PlaceまたはTransportへ結び、`targetDate`を実際の対象日にすること。往路・復路等で対象日が異なる予約は分けること。

Issue #42では作成中の北海道旅行をこの観点で完全再生成した。重複予定、重複Place、移動と予約の不足はJSON修正で解消でき、Schema・UI・新機能の変更は不要だった。
