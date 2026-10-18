# Chat中心の直接操作（#116）

CALが正本管理、直接編集、Chat指示、時刻矛盾、天気、Place補完を所有する。通常のChat全体更新は[専用CLI](chat-schedule.md)を使い、context自動共有・candidate自動採用は行わない。
候補探索・推薦や大きな編集はChatで行い、CAL内AFM推薦・コメントAIを使用しない。

`edit_trip_item(..., changes={"selection": [place_id, ...]})`で候補Placeを明示選択/解除する。
Schemaと参照検証に従い、candidatePlaceIds、予定内容、他Placeを変えない。
候補行の正式採用は`adopt_place_id`を使い、[表示・更新契約](trip-detail-model.md)に従って本文も更新する。

`edit_trip_item(..., changes={"remove_candidate_place_id": place_id})`は指定候補をその予定だけから外す。
候補ID、selection、candidateJudgmentsから同じIDを単一transactionで除外する。
Place本体・他予定・本文・確定状態は保持する。正式採用／選択解除／いいねとは別の単独commandとし、
候補以外のIDや他fieldとの同時更新は拒否する。

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

保存後の通常view再取得は現在値readであり、Chat共有ファイルを更新しない。Chat全体保存は既存の
Validation/atomic adoptionとjournal復旧を使う。正式Trip JSONの移行・削除、DB schema追加は不要。

#116の到達点は通常UIの実装・検証・公式同期と、分離した合成データ環境での再確認準備。物理iPad mini受入・Phase 8終了・リリース判断は#96に残る。

通常コメントを全文編集する利用側はsummaryとdetailsを改行で表示し、変更時は
`normal_comment`と`supporting_details`を同じedit_trip_itemで更新できる。
変更しない保存では元のsummary/detailsを維持し、AI指示はai_instructionだけへ渡す。

## 画面の正式要求（Calendar #238）

Frameの正式writeは`apply_trip_operation(request)`、編集元readは`get_trip_edit_view(trip_id)`、
結果照合は`lookup_chat_request(request_id)`を使う。従来の個別writerは意味検証・部分更新の内部実装として保持する。

requestは`request_id / trip_id / operation / expected_revision / values`の5項目。
revisionは既存Tripの`trip_version / effective_hash / instructions_hash`。viewのrevisionは同じlockで取得した表示内容・未処理指示に対応する。
操作は`item`（source_type/source_item_id/changes）、`day`（day_id/changes）、
`add / delete / reorder`（既存payload）、`location`（place_id/location/expected_location、任意expected_name/googlePlaceId）、
`instruction`（instruction）。各値の意味制約は本書・[表示モデル](trip-detail-model.md)・[地図](map-locations.md)を使う。
prepare、検索、取消は正式writeではない。

要求照合→元版比較→既存の意味検証とOverride/指示保存→既存schedule_receiptsへのreceipt記録を
同じBEGIN IMMEDIATE/接続内で確定する。内部writer/readは呼出元接続に参加し、内部でcommitや通知を行わない。
同ID同内容は後続変更・削除後も元receipt、異内容はConflictError。古い元版もConflictError。
入力拒否はValidationError。DB障害や応答喪失は結果不明としてlookupし、not_foundを未実行の証明にしない。
Trip全体保存の未完journalは既存復旧規則を使い、未解決のまま編集しない。

commit後に`status=committed / resolution=new|replayed / receipt`を返す。receiptは元操作の対象・values・元版/結果版を保持し、
現在viewを含めない。現在値read失敗でも保存確定は失われない。指示を含む操作はinstructions_stateを返す。
指示commitは保存確定であり、pendingは未処理である。AI処理済み・旅程適用済みとは扱わない。
Googleとcommit後通知は新規commitのみ。再送/lookupで再実行せず、表示・Google・DSPの後段失敗で正式保存を繰り返さない。
既存receipt表を使うためschema追加・正式データ移行は不要。切戻しでもreceipt/journal/Overrideを保持し、旧無条件writeへ戻さず画面保存を止める。
