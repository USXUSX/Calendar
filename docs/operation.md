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
2. リポジトリ直下で `python3 scripts/serve_calendar.py` を実行する。
3. `http://127.0.0.1:4174/Sources/web/` を開き、旅行一覧から対象旅行を選ぶ。Calendarはloopback専用の読み取りAPIを通じて、その旅行の `current.json` を直接表示する。
4. 旅程、地図、準備、予約等を閲覧する。
5. 変更しない場合はファイル操作を行わない。

ローカルAPIは通常表示用の `current.json` と候補確認用の `candidate.json` だけを明示的に返し、`history/` やその他の `Calendar_Local` 内容を公開しない。書込みAPIはない。GitHub Pages等の静的レビュー環境ではローカルAPIが存在しないため、コミット済み合成JSONを表示する。

## 4. CalendarからChatへ更新を依頼する

1. Calendarで現在版を表示し、チェック、候補選択、コメントを入力する。
2. 「AI更新依頼をコピー」を押す。
3. コピーされた1パッケージを、そのままChatへ貼り付ける。パッケージには対象旅行名、Trip ID、Chatへの更新指示、採用済みの元 `current.json` 全文、Calendar上の更新材料が含まれる。
4. Chatから、同じスキーマと基本構造を維持した次版完全JSONを受け取る。

パッケージ内の更新指示は次を明記する。

```text
採用済み完全JSONと更新材料を基に、差分や部分JSONではなく、
次版の完全JSONを生成してください。既存JSON上のIDは、同じ対象について維持してください。
通常更新では、採用済みJSONのschemaVersionと基本構造を維持し、表示用の正規化形式へ勝手に変換しないでください。
```

採用済み完全JSONには、画面表示用に正規化したデータではなく元の `current.json` が入る。派生表示項目は元JSON上の安定IDとして扱わず、名称、日付、経路等の特定情報とともに渡す。

## 5. 次版を確認して採用する

1. Chatが返したJSON全体を、対象旅行フォルダの `candidate.json` として保存する。`current.json` はまだ変更しない。
2. `candidate.json` がJSONとして読み取れることを確認する。
3. `candidate.json` の `trip.id` がフォルダ名および `current.json` の `trip.id` と一致することを確認する。
4. 現在版の旅行詳細に表示される「候補版を確認」を開く。
5. 画面上部の「候補版・未採用」を確認し、既存5画面で内容を見る。候補版ではチェック、候補選択、コメント、AI更新依頼等の更新操作はできない。「現在版に戻る」で正本表示へ戻る。
6. 継続する旅行、日、予定、移動、場所、準備、予約等の安定IDが維持され、意図しない欠落や変更がないことを確認する。
7. 採用する場合は、同じ旅行フォルダ内で次の順序を守る。
   1. 現在時刻を使った重複しない名前で、`current.json` を `history/current-YYYYMMDD-HHMMSS.json` へコピーする。
   2. 退避ファイルがJSONとして読み取れ、元の `current.json` と一致することを確認する。
   3. `candidate.json` を `current.json` へ移動する。
   4. 新しい `current.json` のJSON構造、Trip ID、内容を再確認する。

退避が完了する前に `current.json` を上書きしない。採用後は `candidate.json` が残らない状態を正常とする。

本Issue時点では、`candidate.json` の保存、採用、履歴退避は自動化しない。

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
