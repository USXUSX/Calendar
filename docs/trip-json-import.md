# complete Trip JSONの新規取込

Calendar #110。生成と受渡しは[生成ガイド](trip-json-generation.md)、正式構造はSchemaが正本。
Frame `/calendar/import` は共有candidateの選択→Validation→内容確認→登録を主要入口とする。
旧日本語Trip全体の補正UIは置き換える。既存の日本語command/APIは互換用に保持し、
新規主要入口には案内しない。既存Tripへの1予定追加コピペ・条件指定追加は別経路として維持する。

## CAL command

- `list_trip_json_candidates()` はChatGPT共有/CALの直下にあるJSONのファイル名を返す。自動採用しない。
- `read_trip_json_candidate(filename)` はUTF-8 JSONを読み、Schema・semantic Validationと
  ファイル名／Trip ID一致を確認する。`ready / errors / view`、合格時のみ`candidate`を返す。
  不正JSON・読込不能はValidationError、既存IDまたは既存正式ファイルはConflictError。
- `review_trip_json(candidate)` は書込みなしで同じ構造・意味検証と新規ID確認をする。
- `import_trip_json(candidate, confirmed=True)` は画面で確認したsnapshotを再検証して初回採用する。
  共有ファイルの再読込は行わず、確認後の更新を無確認で登録しない。

一覧・読込の`candidate_root`はテスト等の明示指定用。既定は
`/Users/us/マイドライブ/ChatGPT共有/CAL`。HTTPから任意のrootは受け取らない。
親ディレクトリ参照・symlinkは対象にしない。candidateや確認履歴を恒久保存しない。

JSONのID・候補・selection・予約・準備等をそのまま保持し、値を推測・再生成しない。
previewの編集・AI targetは無効。修正はChatでcandidateを更新して再確認する。
登録後のCAL編集を微修正に限定しない。既存TripのChat継続編集は[共有Envelope](trip-json-generation.md#継続するchat往復112)で扱い、本commandの新規ID制約を緩めない。

採用結果は`trip_id / status=adopted / visibility=owner / version=1`。
[既存初回採用](chat-paste-import.md#確認と採用)と同じcreate-if-absentとSQLite transactionを使う。
同一IDの再送・別candidate、未登録でも存在する正式JSONは上書きしない。
書込み・DB失敗時は今回の新規書込みだけを撤回する。

## 確認

`sh Tests/trip-json-import.test.sh` は北海道4日間の合成例で、読込・検証・snapshot採用・全項目保持、
確認必須、不正JSON／Schema／semantic拒否、同一ID・未登録ファイル保護、DB失敗の撤回を確認する。
Frame側は同じCAL commandに対するHTTPとiPad mini相当の代表操作を確認する。
物理端末の実用性・Phase 8振り返り・初期リリース可否は#96でusが判断する。
