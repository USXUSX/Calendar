> Issue #116で廃止。以下は過去の仕様記録であり、公開commandとFrame UIは削除済み。現在は[Chat往復](trip-json-generation.md)を使う。

# 指定情報のコメント追記（Issue #93）

us承認のAFM抽出方式。共通施設取得で保存可能な短い根拠を取得し、施設を確認してから
指定内容を抽出する。抽出previewの明示確認後、対象ScheduleItemの通常コメントへ追記する。
「概要」「営業日」「見どころ」等は同じ自由文instructionで扱い、固定enumにしない。

```python
from Sources.place_acquisition import WikidataAdapter
from Sources.aig_comment_extraction import command_transport

adapter = WikidataAdapter(include_comment_evidence=True)  # 対話callerが再利用
transport = command_transport("/absolute/path/aig-comment-extraction")
acquired = calendar.get_comment_enrichment(trip_id, item_id, place_id, "営業日", adapter)
# 表示して対象施設を確認。1件でも自動同定しない。
preview = calendar.prepare_comment_enrichment(
    trip_id, item_id, acquired, candidate_index, transport, confirmed=True)
# previewのtext、sources、取得日時を表示して確認。no_information / failedでは追記しない。
saved = calendar.append_comment_enrichment(
    command_id, trip_id, item_id, preview, confirmed=True)
```

`place_id`は対象予定の候補またはselectionに属する既存Placeを明示する。別施設や曖昧な
候補を自動選択しない。対象・日・既存コメント・地点入力のsnapshotを操作中だけ保持し、
抽出前後と書込みlock取得後に現行値と比較する。変化はConflictとして再取得へ返す。
同じpreviewの再送もConflictとなり、二重追記しない。Workingとgenerationを変更しない。

取得結果は`confirmation_required / no_information / unavailable`。候補は施設照合用fieldsと
抽出用evidenceを分ける。取得と抽出では書込みなし。抽出previewは
`extracted / no_information / failed`と短文、出典、取得日時、固定失敗コードだけを返し、
根拠本文は含めない。取得結果・previewは内部callerが未変更で保持し、UIから受けるのは
候補indexと確認操作だけ。任意のUI JSONをこれらの引数へ通さない。

`append_comment_enrichment`は既存summaryをそのまま前置し、指定内容、抽出文、出典URL、
帰属表示、取得日時、CC0、および取得時点の情報である旨を通常テキストで追記する。
既存のdetail viewの通常コメントから読める。新しいSchema・履歴・citation保存先は作らない。
対象の`/summary`だけをDirect Overrideでtransaction保存し、全Tripの既存Validationを通す。
失敗はrollback。未完了adoption journalがあればConflictとし、ここでrecoveryしない。
他予定・selection・Place・Trip JSON本体を変更せず、既存Workingは従来のrevision比較でstaleになる。

## 取得・保存条件

`FacilityCandidate.comment_evidence`を既存のpersistable / temporaryとは別に追加した。
各根拠は`text / source / retrieved_at / license / attribution / storage_allowed`を持ち、
CALは明示的な`storage_allowed=True`かつCC0、短文上限、HTTPS出典、有効なtimezone付き取得日時を
確認する。temporaryのdescriptionやlicenseだけから保存許諾を推定しない。
他のlicenseの採用にはadapterとCALの契約変更が必要で、選択や要約で制限を解除しない。

初期取得元は既存Wikidata。opt-in時だけ、保存可能な構造化descriptionと営業曜日P3025・
休業日P3026を短い根拠にする。曜日等のlabelが必要なら追加のまとめ取得を最大1回行う
（全体で最大3直列request、label対象50件まで。超過は営業日根拠なし）。通常の②③⑥取得は従来どおり。
qualified statementやunknown値を含む営業日propertyは全体を省略し、季節・例外条件を落として
通常営業と断定しない。営業期間内の曜日であり、旅行当日の営業保証にはしない。
descriptionに見どころがなければ情報なしでよい。全施設・全情報種別の取得成功は要求しない。
公式URL先の本文取得や外部サイトのスクレイピングは追加しない。

公式資料（2026-09-07確認）:
- [Wikidata Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)：構造化データのCC0。
- [P3025](https://www.wikidata.org/wiki/Property:P3025)：営業期間内の曜日。限定条件を無視しない。
- [共通施設取得](place-acquisition.md)：既存のtimeout、rate limit、保存・一時情報の責務。

## AIG依存と確認範囲

新契約の正本は[AI-Gateway #15](https://github.com/USXUSX/AI-Gateway/issues/15)と
[その実装ブランチのREADME](https://github.com/USXUSX/AI-Gateway/blob/issue-15-comment-extraction/README.md#afm-comment-extraction-boundary-issue-15)。
`aig.comment-extraction.v1`とAFM専用CLIを使用し、AIG PRのmerge前は未リリース依存である。
候補推薦のreasonをコメントへ転用しない。AIGへ渡すのは指定内容と根拠ID・短文だけで、
Trip・既存コメント・予約情報・CAL identity・出典メタデータを渡さない。
形と根拠IDの検査は意味的正しさの保証ではなく、抽出内容は明示確認する。

```sh
python3 -m unittest Tests.test_comment_enrichment Tests.test_place_acquisition Tests.test_conditioned_schedule
```

合成根拠・fake AFM・一時SQLiteだけを使う。実AFM品質、live取得品質、Frame画面接続、
実機受入、production、Calendar_Local実データ変更は未実施。Frameは後続の対応Issueで
上記の意味commandを接続し、本文やSQLiteを直接書き換えない。
