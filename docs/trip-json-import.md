# complete Trip JSONの新規取込

Calendar #110。生成と受渡しは[生成ガイド](trip-json-generation.md)、正式構造はSchemaが正本。
Frame `/calendar/import` は共有candidateの選択→Validation→内容確認→登録を主要入口とする。
旧日本語Trip全体の補正UIは置き換える。既存の日本語command/APIは互換用に保持し、
新規主要入口には案内しない。既存Tripへの1予定追加コピペ・条件指定追加は別経路として維持する。

## CAL command

- `list_trip_json_candidates()` はCalendar_Chat直下のTripフォルダにある`candidate.json`を、`<trip-id>/candidate.json`の相対名で返す。`context.json`や旧直下JSONは対象にしない。自動採用しない。
- `read_trip_json_candidate(filename)` はUTF-8 JSONを読み、Schema・semantic Validationと
  親フォルダ名／Trip ID一致を確認する。`ready / errors / view`、合格時のみ`candidate`を返す。
  不正JSON・読込不能はValidationError、SQLite登録済みIDはConflictError。
- `review_trip_json(candidate)` は書込みなしで同じ構造・意味検証と新規ID確認をする。
- `import_trip_json(candidate, confirmed=True)` は画面で確認したsnapshotを再検証して初回採用する。
  共有ファイルの再読込は行わず、確認後の更新を無確認で登録しない。

一覧・読込の`candidate_root`はテスト等の明示指定用。既定は
domainの`chat_root`（未指定時は`/Users/us/Tools/GoogleDrive/Calendar_Chat`）と共通。HTTPから任意のrootは受け取らない。
新規candidateはcomplete JSON本体であり、既存Trip用Envelopeは受け付けない。
親ディレクトリ参照・多段の下位フォルダ・Tripフォルダやcandidateのsymlinkは対象にしない。candidateや確認履歴を恒久保存しない。

JSONのID・候補・selection・予約・準備等をそのまま保持し、値を推測・再生成しない。
previewの編集・AI targetは無効。修正はChatでcandidateを更新して再確認する。
登録後のCAL編集を微修正に限定しない。既存TripのChat継続編集は[共有Envelope](trip-json-generation.md#継続するchat往復112)で扱い、本commandの新規ID制約を緩めない。

採用結果は`trip_id / status=adopted / visibility=owner / version=1`。
[既存初回採用](chat-paste-import.md#確認と採用)と同じSQLite transactionを使い、SQLite登録済みTripは上書きしない。
SQLite未登録なのにformal Trip JSONだけ残る孤立状態は正式Tripとして扱わず、内容確認済みの新規取込時にcandidateへ置換して登録する。
同一IDがSQLite登録済みなら再送・別candidateとも拒否する。書込み・DB失敗時は今回の新規書込みを撤回する。

## 確認

`sh Tests/trip-json-import.test.sh` は北海道4日間の合成例で、読込・検証・snapshot採用・全項目保持、
確認必須、不正JSON／Schema／semantic拒否、孤立formal JSONの置換、登録済みID保護、DB失敗時の新規書込み撤回を確認する。
Frame側は同じCAL commandに対するHTTPとiPad mini相当の代表操作を確認する。
物理端末の実用性・Phase 8振り返り・初期リリース可否は#96でusが判断する。
