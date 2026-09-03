# CAL開発ロードマップ

この文書は、CALの最終利用像と開発の階層を示す短い正本である。先の計画は粗く保ち、現在のPhaseだけをStepへ分解する。

## 最終利用像

CALは、次の3領域を内部機能としては十分に分離しつつ、表示上は関連付けて扱う。

1. 家庭内で共有する範囲のスケジュール管理
2. 主にus個人のタスク管理
3. 旅程管理を中核とする旅行計画、修正、共有、旅行Todo、将来の旅行記録

## 共通設計思想

- 個人用としてusが使いやすいことを最優先し、業務システムのような厳密さや全ケース対応を求めない。
- 必要な機能を使いやすくし、あらゆるケースを先回りして専用機能にしない。
- データ構造の最低限の整合は保つ一方、内容は広く許容し、想定外の状態でも可能な範囲で表示する。
- 不自然な状態はusが補正できる経路を優先し、必要性が明らかになった専用機能だけを後から追加する。
- 内部基盤として自然な情報は保持してよいが、FRM等のユーザー画面には必要最小限だけを表示する。

## 旅程管理のGoal

| Goal | 目的 | 完了イメージ | 主要境界 |
| --- | --- | --- | --- |
| 1. 旅程詳細画面を実用完成 | 旅行中に必要な旅程情報を把握し、計画と修正を一つの流れで扱えるようにする | iPad mini / iPadで旅程を実用的に閲覧でき、直接編集、AI指示、候補追加・判断の最低限の操作まで行える | 旅程詳細を対象とし、地図、CAL全体のTodo、旅行記録の完成は後続Goalに分ける。画面からSQLiteやTrip JSONを直接操作しない |
| 2. 地図機能を実用完成 | 旅程の場所と移動を空間的に把握し、詳細画面だけでは難しい旅行中の判断を支える | 旅程の場所・移動と地図が自然に対応し、計画時と旅行中に必要な確認ができる | 地図は旅程の別正本にせず、CALが保持する旅程から表示する。地図provider、navigation連携、公開方式は実装Phaseで必要な範囲だけ決める |
| 3. 旅行TodoをCAL全体のTodoとの関係で整理・実装 | 旅行準備を旅程内だけに閉じず、us個人のTodo管理の中でも扱えるようにする | 旅行に属するTodoを旅程とCAL全体の双方から一貫して確認・更新できる | CALのドメイン用語は`Todo`とし、TSKの`Job`と混同しない。Todoの正本を旅程表示用に重複させず、participant共有は必要時に別途決める |
| 4. 旅程記録・過去旅行閲覧を実装 | 計画した旅程を旅行後の記録として残し、過去の旅行を再び参照できるようにする | 予定と実際の記録を必要な範囲で区別し、過去旅行を探して閲覧できる | 記録項目、写真等のmedia、保存方式、共有範囲は先回りして固定しない。既存実データの移行は別の明示的な作業とする |

## Goal 1: 旅程詳細画面を実用完成する

### Phase

| Phase | 状態 | 目的 | 完了イメージ | 主要境界 |
| --- | --- | --- | --- | --- |
| 1. 旅程詳細UIの完成像を確定 | 完了 | 後続実装の判断基準となる情報構成、状態表現、主要操作を決める | 対象端末での表示方針と、閲覧・編集・候補等の入口を一つの完成像として確認できる | 確定要求は `docs/trip-detail-ui.md` に保持し、比較案や細かな調整値を恒久仕様にしない |
| 2. UIに合わせて旅程データ・表示モデルを整理 | 完了 | Phase 1の完成像を、既存の旅程正本とCAL境界から無理なく表示できるようにする | 画面に必要な情報、状態、関係を表示モデルから取得でき、不足や変換規則が明確になっている | formal Trip JSON、SQLite、effective Tripの正本境界を維持し、UI都合の二重正本や将来向けの過剰な汎用化を作らない |
| 3. 直接編集を完成 | 完了 | usが具体的な値を編集画面で補正できる実用的な経路を完成する | 予定選択から端末別編集画面、Validation、反映状態の確認まで一つの流れで行える | owner-facing UIはFRMが担い、CALの意味ベースのcommandとDirect Overrideを通す。SQLiteやTrip JSONを画面から直接変更せず、曖昧な変更意図はAI指示と分ける |
| 4. Working Trip編集基盤 | 完了 | authoritative Tripを壊さず、未確定変更を自由に保持・表示・再編集・出力できるようにする | 既存予定の変更・削除予定化、新規予定の仮追加、day-level指示を最新Working状態として扱い、D案UIとChat向け出力から利用できる | Workingは履歴を積まず、formal Trip完全適合や内容の完全整合を要求しない。authoritative Trip、Direct Override、表示モデルの既存責務を保ち、ケース別commandを増やしすぎない |
| 5. Working Trip確定フロー | 完了 | Workingを反映したcomplete Trip candidateをCAL内で安全に正式Tripへ戻す | Working exportから作成したcomplete candidateをformal Validationし、staleでないことを確認してauthoritative Tripへatomic adoptionし、成功後だけWorkingをclearしてFRMへ結果を返せる | CALはcandidate受入れ、Schema・semantic Validation、captured revisionに対するstale確認、all-or-nothingのadoptionを所有する。candidate生成元を契約へ持ち込まず、失敗時はauthoritative TripとWorkingを変更しない |
| 6. AI接続を実用化 | 現在 | Working exportからcomplete Trip candidateを生成・再構成する部分を、安全な外部generator境界へ接続する | usが生成を開始し、返されたcandidateを確認したうえで、Phase 5の受入れ境界へ変更せず渡して確定結果をFRMで把握できる | 自動化はexport packageの受け渡し、complete candidate生成、FRMへの返却までとし、確定操作、stale時の再編集・再export、内容判断は手動に残す。provider、model、credentialはCAL coreへ入れず、CAL外の旅行計画正本更新も自動化しない |
| 7. 候補・特殊ケースを実利用で整理 | 未着手 | Working Trip方式で候補や複数予定変更等をどこまで自然に扱えるか確認する | 候補追加・判断・選定、複数予定変更、別行動等で既存Working編集に不足するものだけが明確になる | 専用機能を先回りして増やさず、既存経路で足りる場合は小さく完了してよい |
| 8. 実利用でUI・運用を仕上げる | 未着手 | 対象端末、Chat往復、自動確定の使い勝手を実利用で仕上げる | iPad mini / iPad、Safari / Chromeで主要経路を継続利用でき、Working状態表示や確認導線の支障が取り除かれている | font、余白、icon等は実利用から調整し、Review Handoffを含む確認導線を確認する。全ケース対応を完了条件にしない |

### 完了したPhase 5: Working Trip確定フロー

1. **完了（us確認済み）**: candidate受入れ・確定境界を確定する。
2. **完了（us確認済み）**: complete candidate受入れを実装する。
3. **完了（us確認済み）**: stale確認を確定ゲートへ接続する。
4. **完了（us確認済み）**: formal Validationを確定する。
5. **完了（us確認済み）**: atomic adoptionとWorking後始末を実装する。
6. **完了（us確認済み）**: Chat手動往復の受入れを合成データで確認する。
7. **完了（us確認済み）**: FRMの最小確定導線を実装する。
8. **完了（us確認済み）**: Phase 5全体を合成データでValidationする。
9. **完了**: Phase 5を振り返り、Phase 6のAI接続境界を再確認する。

Phase 5で確立した一連の境界は、Working export → generator-neutralなcomplete candidate → CAL Validation → captured effective revisionのstale gate → atomic adoption → 成功後だけWorking clear → FRMでのsuccess / stale / Validation結果表示である。candidateの作成経路にかかわらず、Phase 6もこの境界を迂回・重複実装しない。

### 現在のPhase 6: AI接続を実用化

#### 自動化する範囲

- CALの既存Working export packageを、provider-neutralな外部generatorへ変更せず渡す。
- generatorが返す出力を1件のcomplete Trip candidate JSONとしてFRMへ戻す。
- usの確定操作後はPhase 5の`adopt_working_trip_candidate()`へcandidateを変更せず渡し、既存のValidation、stale gate、atomic adoption、Working clear、結果表示をそのまま利用する。
- AI/provider失敗、形式不正、stale、Validation失敗を区別し、再試行や採用を暗黙に行わずWorkingを保持する。

#### 引き続き手動に残す範囲

- Working内容と自然言語指示の作成・補正、および生成されたcomplete candidateの内容確認。
- FRMからの最終確定操作。candidate生成成功だけではauthoritative Tripを変更しない。
- stale時の差分判断、Working再編集、再export、再生成。自動rebase・自動mergeは行わない。
- provider/model/credentialの選択・管理、CAL外の旅行計画正本更新、実運用activation。
- 手動Chat往復は、自動経路が利用できない場合と生成内容を対話的に補正したい場合の有効な経路として残す。

#### 前提

- generatorの入力正本はPhase 4のWorking export package、採用正本はPhase 5のcomplete candidate受入れ境界とする。
- CAL coreとFRMはprovider固有payload、model、credential、prompt運用を所有しない。
- AI出力は未信頼candidateであり、既存CAL Validationより前にauthoritative TripまたはWorkingを変更しない。
- Phase 6ではAIG/API接続を実装するが、自動確定、高度なdiff、常駐workflow、CAL外同期は別の判断なしに追加しない。

#### 実装前に決める未決事項

1. 最初の接続先をAIGとするか、既存の外部generator command / API adapterを直接利用するか。
2. FRMの生成開始・candidate確認導線を、現行の最小確定UIへどこまで追加するか。
3. generator失敗時に同一要求を再試行可能にする最小状態をどこが保持するか。自動retryは前提にしない。

完了したPhase 2・3の表示・入力・更新契約は[`trip-detail-model.md`](trip-detail-model.md)に保持する。

## 正本と一時Context

このロードマップには最終利用像、Goal、Phase、現在PhaseのStepだけを残す。PhaseやStep途中の比較案、仮判断、レビュー結果は、現在PhaseのGitHub Issue等の一時的な作業単位で扱い、恒久文書へ逐次蓄積しない。

Phase終了時に振り返りを行い、今後も必要な確定事項だけを、このロードマップ、仕様、Decision等の適切な正本へ反映する。その際に後続Phaseと、必要ならGoalも見直す。一時Context専用の恒久文書は作らない。
