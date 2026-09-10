# Chat中心の直接操作（#116）

CALが正本管理、直接編集、Chat指示/context、candidate確認・反映、時刻矛盾、天気、Place補完を所有する。
候補探索・推薦や大きな編集はChatで行い、CAL内AFM推薦・コメントAIを使用しない。

`edit_trip_item(..., changes={"selection": [place_id, ...]})`で候補Placeを明示選択/解除する。
Schemaと参照検証に従い、candidatePlaceIds、予定内容、他Placeを変えない。

`change_trip_schedule(command_id, trip_id, action, payload)`は以下の通常操作を扱う。

- add: 任意after_item_idを指定すると同日のその予定/移動の直下へ挿入する。対象が消えていれば保存しない。省略時は末尾。day_idとtitle/category/start/end/normal_comment、任意status/show_duration、place_nameまたは未定時のsearch_query。時刻は表示・更新契約のCAL変換を使う。場所も条件も未入力なら本文をsearchQueryへ保持し、本文だけで追加できる（分割・場所の自動生成なし）。
- add（コピペ）: day_idとtext。既存の日本語ラベル形式で予定を1件だけ記す。未解決行・不足・別日・複数予定は保存せず、貼付内容の修正を求める。
- delete: day_idとsource_item_id。Todoから参照中の予定は解除が先。Placeや予約情報は削除しない。
- reorder: day_idと、その日の全予定・移動を並べたitem_ids。

追加は既存のstable ID structural Direct Override、削除は同じmember pathのnullとして保存する。
削除する予定のfield Overrideは非activeにし、削除memberはfield適用後に処理する。
移動削除はtransportIdsも同一transactionで更新する。並び替えは各itemのorderだけを更新する。
各commandは現在のeffective Tripで対象とSchema/参照を確認し、単一transactionで保存する。
Workingは作成・変更しない。既存Workingのstaleは従来のrevision比較に従う。

保存後の通常view再取得でChat contextを更新する。Chat candidateの正式採用は既存の
Validation/atomic adoptionを使う。正式Trip JSONの移行・削除、DB schema追加は不要。

#116の到達点は通常UIの実装・検証・公式同期と、分離した合成データ環境での再確認準備。物理iPad mini受入・Phase 8終了・リリース判断は#96に残る。
