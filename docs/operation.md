# Calendar 実運用手順

## 1. 対象と原則

本書は、実旅行データを閲覧し、Calendarで作った変更指示をChatへ渡し、Chatが返した次版の完全JSONを確認して採用する手順を定める。

実データは私有領域 `/Users/us/Tools/LocalData/Calendar_Local` だけに置く。GitリポジトリやGoogle Driveへコピー、コミット、アップロードしない。Calendarは採用済み完全JSONを直接編集せず、差分や部分JSONも正本にしない。

## 2. 配置とファイルの役割

旅行ごとに、変更しない安定した `trip.id` をフォルダ名に使う。

```text
Calendar_Local/
  trips/
    <trip-id>/
      current.json
      candidate.json        # 次版の確認中だけ存在
      history/
```

- `current.json`: 現在の採用済み完全JSON。実運用上の唯一の正本。
- `candidate.json`: Chatが生成した次版の完全JSON。確認前の候補であり、正本ではない。
- `history/`: 採用時に、直前の `current.json` を退避する場所。`current-YYYYMMDD-HHMMSS.json` の形式で保存する。

`candidate.json` は必要なときだけ作る。`history/` に候補版や一時状態を保存しない。画面上のチェック、候補選択、コメントは一時状態であり、`current.json` を変更しない。ブラウザを閉じる前に、必要な更新材料を必ずコピーする。

## 3. 通常閲覧

1. 対象旅行のフォルダ名と `current.json` 内の `trip.id` が一致することを確認する。
2. Calendarで `current.json` を読み取り専用で開く。
3. 旅程、地図、準備、予約等を閲覧する。
4. 変更しない場合はファイル操作を行わない。

現行の静的プロトタイプは、まだ `Calendar_Local` の実データを直接選択して表示しない。実データ読込は次の実装Issueで扱う。それまでは `current.json` を正本として維持し、本書の更新手順を使う。

## 4. CalendarからChatへ更新を依頼する

1. Calendar上でチェック、候補選択、コメントを入力する。
2. 「AI更新材料をコピー」で更新材料をコピーする。現行版は変更材料だけを出力するため、次の4要素をそろえて1パッケージとしてChatへ渡す。
   - 対象旅行名
   - Trip ID
   - 対象旅行の採用済み `current.json` 全文
   - Calendarでコピーした更新材料
3. 次の指示を明記する。

```text
採用済み完全JSONと更新材料を基に、差分や部分JSONではなく、
次版の完全JSONを生成してください。既存の安定IDは、同じ対象について維持してください。
```

採用済み完全JSON本体を省略しない。更新材料だけでは、Chatは欠けていない次版完全JSONを確実に生成できない。

## 5. 次版を確認して採用する

1. Chatが返したJSON全体を、対象旅行フォルダの `candidate.json` として保存する。`current.json` はまだ変更しない。
2. `candidate.json` がJSONとして読み取れることを確認する。
3. `candidate.json` の `trip.id` がフォルダ名および `current.json` の `trip.id` と一致することを確認する。
4. 継続する旅行、日、予定、移動、場所、準備、予約等の安定IDが維持され、意図しない欠落や変更がないことを確認する。
5. Calendarで候補版を表示できる実装後は、候補版の全画面と更新指示の反映内容を確認する。それまではJSON全体を確認する。
6. 採用する場合は、同じ旅行フォルダ内で次の順序を守る。
   1. 現在時刻を使った重複しない名前で、`current.json` を `history/current-YYYYMMDD-HHMMSS.json` へコピーする。
   2. 退避ファイルがJSONとして読み取れ、元の `current.json` と一致することを確認する。
   3. `candidate.json` を `current.json` へ移動する。
   4. 新しい `current.json` のJSON構造、Trip ID、内容を再確認する。

退避が完了する前に `current.json` を上書きしない。採用後は `candidate.json` が残らない状態を正常とする。

## 6. 不採用と復旧

不採用の場合は `candidate.json` だけを削除し、`current.json` と `history/` は変更しない。Calendarの一時状態も破棄する。

採用後に問題が見つかった場合は、`history/` から戻す版を日時と内容で特定する。現在の `current.json` も新しい履歴名で退避してから、戻す版を `current.json` へコピーする。復旧後にJSON構造、Trip ID、内容を再確認する。履歴ファイルそのものは移動・削除せず残す。

## 7. 新規旅行を作る入口

1. Chatへ、旅行名、期間、分かっている予定、候補、準備・予約情報と、Calendarの完全JSON仕様に従うよう依頼する。
2. Chatから最初の完全JSONを受け取る。差分や部分JSONは受け取らない。
3. 完全JSON内の一意で安定した `trip.id` を確認し、`Calendar_Local/trips/<trip-id>/history/` を作る。
4. 完全JSONをまず `candidate.json` として配置し、JSON構造、Trip ID、安定ID、内容を確認する。
5. 初回採用時は退避対象の `current.json` がないため、承認した `candidate.json` を `current.json` にする。

新規旅行でも、自動同期、外部公開、GitやGoogle Driveへの実データ保存は行わない。
