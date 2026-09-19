# Calendar運用入口

通常の旅程操作はFrameを利用します。生成形式と受渡しの詳細は[生成ガイド](trip-json-generation.md)、新規採用は[JSON取込契約](trip-json-import.md)が正本です。

## 保存先と所有者

| 保存先 | 内容・所有者 |
| --- | --- |
| `/Users/us/Tools/LocalData/Calendar_Local` | 正式Trip JSON・SQLite。CALだけが更新する |
| `/Users/us/マイドライブ/Tools/Calendar_Chat` | CALがcontextを共有し、Chatがcandidateを返す運用授受先 |
| `/Users/us/マイドライブ/Tools/Calendar_GD` | Gitから一方向同期するコード・仕様の参照コピー |

正式Trip／SQLiteをGitや参照コピーへ入れません。Chatは正式保存先を直接変更せず、運用授受先だけを使います。

## 自宅の共通設定

固定の住所と座標は`Calendar_Local/settings/home.json`で管理する。各旅行の「自宅」はこの値を共通利用し、旅行ごとの位置修正は行わない。詳細は[固定の自宅](map-locations.md#固定の自宅)を参照する。

## 新規Tripと通常操作

1. Chatに現行Schemaと生成ガイドを渡し、complete Trip JSONを作成する。
2. 生成ガイドの手順で`Calendar_Chat/<trip-id>/candidate.json`へ受け渡す。
3. Frameの`/calendar/import`で読み込み、CALのValidation結果と旅程内容を確認して登録する。不正ならChatで修正して再確認する。
4. `/calendar/trips`の一覧から旅程を開く。編集ONで予定・日別情報を編集し、「変更を保存」で反映する。予定追加・削除・並び替え、候補の正式採用／選択解除も通常画面で行う。

取込後の編集は微修正に限定しません。意味更新と保存はCALへ委譲し、Frameは正式JSONやSQLiteを直接操作しません。

## 既存TripのChat往復

CALが最新旅程と未処理指示を`context.json`へ共有します。Chatはこのcontextから既存Trip用Envelopeの`candidate.json`を作成します。新規登録用のcomplete JSON単体を既存Trip用Envelopeの代わりに置きません。

通常load/reloadは読み取り専用ではありません。CALがcandidateを検証し、有効なら正式採用します。invalid/staleなら正式旅程を保ち、修正または最新contextからの再生成を案内します。指示・revision・採用条件は[継続Chat往復](trip-json-generation.md#継続するchat往復112)を参照してください。

Place補完は対象施設と保存値を確認して採用します。取得できない値は未補完のまま扱います。天気は予報期間内の座標・対象日に対応する一時情報です。契約は[Place取得・採用](place-acquisition.md)と[表示・更新契約](trip-detail-model.md)を参照してください。

## 保持している旧経路

以下は通常運用の開始手順ではありません。既存コード・データは削除せず保持しています。

- **read-only prototype**: `python3 scripts/serve_calendar.py`でloopbackの`http://127.0.0.1:4174/Sources/web/`を開く。正式`trips/<trip-id>.json`だけを読むため、Frameが扱うSQLiteのDirect Overrideを含むeffective Trip表示とは区別する。
- **Working／AIG再生成**: 保存・Validation・stale・atomic adoption基盤を保持する。通常UIからは外しており、契約は[表示・更新契約](trip-detail-model.md)に残す。
- **AI Instruction Patch worker**: `scripts/run_generation_worker.py`が明示DB・Trip root・generatorを使うone-shot経路。`scripts/generate_openai_patch.py`は保持adapterであり、通常のChat往復の必須構成ではない。実API・定期実行の有効化は別の運用判断とする。

採用中断時の復旧もCALが所有します。`.adoption/`のstaging／journalやSQLiteを手作業で変更せず、`recover_trip_adoption()`等の既存契約に従います。自動収束できない不一致はConflictとして扱います。
