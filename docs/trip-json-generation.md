# ChatGPT向け旅行JSON生成ガイド

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

生成物を説明文から切り離したUTF-8 JSONファイルとして保存し、次を実行する。

```sh
python3 scripts/validate_trip.py /path/to/generated-trip.json
```

エラーがあれば該当パスとエラーだけをChatGPTへ返し、同じ完全JSONを修正させる。検証成功後に`Calendar_Local/trips/<trip-id>.json`へ配置し、Calendarの一覧、旅程、地図、準備、コメントを確認する。Calendar側で欠損値の補完や旧形式変換は行わない。
