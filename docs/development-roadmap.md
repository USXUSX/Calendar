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
| 1. まず使えるCALを初期リリース | Chatで完成に近い旅程を作り、CALで取込・表示・細部仕上げを行う | 新規Trip貼付、基本表示・手動編集、日別代表エリア、限定時刻矛盾表示、1件ずつの予定・候補追加、コメント・地点補完、予報期間内の天気を使える | 操作中の予定以外を自動変更しない。移動時間込み整合性、固定予約保護、OpenAI旅程生成・再生成は対象外。詳細は[初期リリース仕様](initial-release.md) |
| 2. 地図機能を実用完成 | 旅程の場所と移動を空間的に把握し、詳細画面だけでは難しい旅行中の判断を支える | 旅程の場所・移動と地図が自然に対応し、計画時と旅行中に必要な確認ができる | 地図は旅程の別正本にせず、CALが保持する旅程から表示する。地図provider、navigation連携、公開方式は実装Phaseで必要な範囲だけ決める |
| 3. 旅行TodoをCAL全体のTodoとの関係で整理・実装 | 旅行準備を旅程内だけに閉じず、us個人のTodo管理の中でも扱えるようにする | 旅行に属するTodoを旅程とCAL全体の双方から一貫して確認・更新できる | CALのドメイン用語は`Todo`とし、TSKの`Job`と混同しない。Todoの正本を旅程表示用に重複させず、participant共有は必要時に別途決める |
| 4. 旅程記録・過去旅行閲覧を実装 | 計画した旅程を旅行後の記録として残し、過去の旅行を再び参照できるようにする | 予定と実際の記録を必要な範囲で区別し、過去旅行を探して閲覧できる | 記録項目、写真等のmedia、保存方式、共有範囲は先回りして固定しない。既存実データの移行は別の明示的な作業とする |

## Goal 1: まず使えるCALを初期リリースする

Issue #85のus採否判断とIssue #86の仕様承認により範囲を更新した。完成条件・貼付形式・外部取得方針は[初期リリース仕様](initial-release.md)を正本とする。2026-09-16、usの基本検証完了の申告と全体完了指示に基づき、Issue #96でGoal 1／Phase 8を一旦完了し、実利用・保守へ移行する。

### Phase（1〜7は従来方針での実施履歴）

Phase 1〜7の完了記録と既存AI経路は保持する。Phase 6〜7のAI生成・再生成の完成や追加検証は、現行Goal 1の完成条件ではない。

| Phase | 状態 | 目的 | 完了イメージ | 主要境界 |
| --- | --- | --- | --- | --- |
| 1. 旅程詳細UIの完成像を確定 | 完了 | 後続実装の判断基準となる情報構成、状態表現、主要操作を決める | 対象端末での表示方針と、閲覧・編集・候補等の入口を一つの完成像として確認できる | 確定要求は `docs/trip-detail-ui.md` に保持し、比較案や細かな調整値を恒久仕様にしない |
| 2. UIに合わせて旅程データ・表示モデルを整理 | 完了 | Phase 1の完成像を、既存の旅程正本とCAL境界から無理なく表示できるようにする | 画面に必要な情報、状態、関係を表示モデルから取得でき、不足や変換規則が明確になっている | formal Trip JSON、SQLite、effective Tripの正本境界を維持し、UI都合の二重正本や将来向けの過剰な汎用化を作らない |
| 3. 直接編集を完成 | 完了 | usが具体的な値を編集画面で補正できる実用的な経路を完成する | 予定選択から端末別編集画面、Validation、反映状態の確認まで一つの流れで行える | owner-facing UIはFRMが担い、CALの意味ベースのcommandとDirect Overrideを通す。SQLiteやTrip JSONを画面から直接変更せず、曖昧な変更意図はAI指示と分ける |
| 4. Working Trip編集基盤 | 完了 | authoritative Tripを壊さず、未確定変更を自由に保持・表示・再編集・出力できるようにする | 既存予定の変更・削除予定化、新規予定の仮追加、day-level指示を最新Working状態として扱い、D案UIとChat向け出力から利用できる | Workingは履歴を積まず、formal Trip完全適合や内容の完全整合を要求しない。authoritative Trip、Direct Override、表示モデルの既存責務を保ち、ケース別commandを増やしすぎない |
| 5. Working Trip確定フロー | 完了 | Workingを反映したcomplete Trip candidateをCAL内で安全に正式Tripへ戻す | Working exportから作成したcomplete candidateをformal Validationし、staleでないことを確認してauthoritative Tripへatomic adoptionし、成功後だけWorkingをclearしてFRMへ結果を返せる | CALはcandidate受入れ、Schema・semantic Validation、captured revisionに対するstale確認、all-or-nothingのadoptionを所有する。candidate生成元を契約へ持ち込まず、失敗時はauthoritative TripとWorkingを変更しない |
| 6. AI接続を実用化 | 完了 | Working exportからcomplete Trip candidateを生成・再構成する部分をAIGへ接続する | auto policyでは既存Phase 5 gateを通して自動採用し、review policyではcandidate確認後に同じgateから採用でき、結果をFRMで把握できる | CALが最新1件のgeneration stateとcandidateを所有し、AIGはstateless、FRMは表示・操作に限定する。provider、model、credentialはAIG側へ閉じ、stale解消・自動retry・CAL外正本更新は行わない |
| 7. 候補・特殊ケースを実利用で検証 | 完了（限定付き） | 現行Working指示とAIG再生成で候補や複数予定変更等をどこまで自然に扱えるか実利用で確認する | 候補追加・判断・選定、複数予定変更、別行動等について、既存経路で足りる範囲と実際に不足する範囲が明確になる | 候補・特殊ケースの専用機能を先回りして追加しない。不足が実利用で確認されたものだけを後続Issueで追加する |
| 8. 実利用でUI・運用を仕上げる | 完了（2026-09-16、Issue #96） | Chat貼付からCALの細部仕上げまでを実用化する | 初期リリース仕様の採用機能を実装し、対象端末で実用性を確認できる | 新規Tripは内容確認後に採用し、既存TripのChat candidateは通常load/reloadでValidation後に自動採用する。直接操作は対象だけを更新する |

### 完了したPhase 5: Working Trip確定フロー

1. **完了（us確認済み）**: candidate受入れ・確定境界を確定する。
2. **完了（us確認済み）**: complete candidate受入れを実装する。
3. **完了（us確認済み）**: stale確認を確定ゲートへ接続する。
4. **完了（us確認済み）**: formal Validationを確定する。
5. **完了（us確認済み）**: atomic adoptionとWorking後始末を実装する。
6. **完了（us確認済み）**: Chat手動往復の受入れを合成データで確認する。
7. **完了（us確認済み）**: FRMの最小確定導線を実装する。
8. **完了（us確認済み）**: Phase 5全体を合成データでValidationする。
9. **完了（us確認済み）**: Phase 5を振り返り、Phase 6のAI接続境界を再確認する。

Phase 5で確立した一連の境界は、Working export → generator-neutralなcomplete candidate → CAL Validation → captured effective revisionのstale gate → atomic adoption → 成功後だけWorking clear → FRMでのsuccess / stale / Validation結果表示である。candidateの作成経路にかかわらず、Phase 6もこの境界を迂回・重複実装しない。

### 完了したPhase 6: AI接続を実用化

1. **完了（us確認済み）**: AIG接続境界と最小generation stateを確定する。
2. **完了（us確認済み）**: CALにWorking Tripごとの最新generation stateとcandidateを実装する。
3. **完了（us確認済み）**: AIGにWorking exportからcomplete candidateを1件返すstatelessな最小生成境界を実装する。
4. **完了（us確認済み）**: CAL → AIG → Phase 5 candidate受入れを接続する。
5. **完了（us確認済み）**: `auto / review` adoption policyを実装する。
6. **完了（us実機確認済み）**: FRMに生成開始と`generating / failed / candidate_ready / adopted`の最小表示・操作を追加する。
7. **完了（us確認済み）**: AIG生成失敗、複雑な変更、ユーザー判断が必要な場合も、既存のWorking export → Chat手動調整 → complete candidate → Phase 5 adoptionへ戻れることを合成データで確認する。
8. **完了（us確認済み）**: auto / review、stale、malformed / Validation failure、AIG failure、Working clearを合成データと必要なブラウザ確認でValidationする。
9. **完了（us確認済み）**: Phase 6を振り返り、確立した責務・policy・fallbackを確定し、Phase 7を実利用による不足確認のPhaseとする。

Step 1で、最初の接続先をAIGとし、CAL → AIG requestはgeneration identityと既存Working export package、AIG → CAL resultは同じidentityとcomplete Trip candidate 1件だけを運ぶprovider-neutral契約に確定した。CALはTripごとの最新1件だけを`generating / candidate_ready / failed / adopted`として所有し、policyはgeneration開始時に`auto / review`から選ぶ。Issue #80で現在の採用方針として扱い、限定rule検出時だけauto→reviewへ原子的に昇格する。AIGはworkflow stateを保持せず、FRMも正本stateやcandidateを持たない。

`auto`はAIG返却後にPhase 5のValidationを通し、限定rule未検出ならstale gate / atomic adoptionへ進み、検出時は同じgenerationをreviewへ昇格する。`review`はcandidateをCALの`candidate_ready`へ保持してusの確定操作後に同じ境界へ渡す。どちらもPhase 5 gateを迂回せず、失敗時はWorkingを保持する。新しい手動実行は最新の終端stateを置き換えるが、自動retry、queue、履歴、staleの自動rebase / mergeは設けない。手動Chat fallback、CAL外旅行計画正本更新、production activationはこのstate machineの外に保つ。

Step 7では、AIGのsafe failure後もWorkingとraw user intentが既存exportから取得でき、Chatで手動調整したcomplete candidateをgeneration stateとは独立したPhase 5のValidation / stale gate / atomic adoptionへ渡せることを合成データで確認した。複雑な変更やユーザー判断が必要な場合も同じ既存経路を利用し、自動Chat送信、Chat session管理、新しいfallback stateや機構は追加しない。

### 限定付き完了したPhase 7: 候補・特殊ケースを実利用で検証

[Issue #77](https://github.com/USXUSX/Calendar/issues/77)のus判断により限定付き完了とする。代表ケースを一通り確認し、既存Working＋AIG経路で扱える範囲と、complete-Trip生成による不要な既存データ変更を区別した。候補・別行動の専用schema / command / UIやparticipant scopeを追加する根拠は得られていない。

保持性の不足にはIssue #80 / PR #81で限定3 ruleと同一generationのauto→review昇格を実装した。検出時は既存review確認へ合流し、採用は引き続きPhase 5のValidation / stale gate / atomic adoptionを通す。ruleの契約は[`trip-detail-model.md`](trip-detail-model.md)を参照する。

自由文意図の未達、未指定field、Place / Day等の検出外は残余リスクとして受け入れる。一般的な生成安定性、全ケースでのadoption成功、過去の保存していないcandidateの原因復元を保証・完了条件とせず、追加liveで追跡しない。同種の不要変更が実利用で繰り返される領域だけ、将来のscope指定／固定rule化を局所的に検討する。

### 完了したPhase 8: 実利用でUI・運用を仕上げる

新規Tripはcomplete JSONの生成・確認・取込、既存TripはFrameの直接編集とCAL↔Chatの継続往復を主要経路として仕上げた。候補探索・大きな旅程変更はChatへ寄せ、旧Working／AI編集UIを外した。旅程表示・候補操作・Place補完・天気の仕上げ、旅程一覧、CSSと旧説明の整理を完了した。授受先は`/Users/us/マイドライブ/Tools/Calendar_Chat`、正式Trip／SQLiteとGit参照コピーは分離する。

#124の物理iPad miniレビュー「概ねOK」、#126の新規Trip主要経路確認、その後のproduction反映・外部確認記録と、usの基本検証完了の申告を終了判断の根拠とする。終了時の合成確認は実機受入の再実施やcloud Drive同期そのもののE2Eを意味しない。詳細は[Issue #96](https://github.com/USXUSX/Calendar/issues/96)に残す。

現在の範囲では全面再構築は不要。Goal 2以降の地図・旅行Todo・記録、メール取込、旧Working／OpenAI経路の追加開発、[AIG #12の保持性調査](https://github.com/USXUSX/AI-Gateway/issues/12)は保留し、次の旅行等で必要が確認された場合に再判断する。全ケース対応や初期rule検出外の先回り実装は行わない。既存データや旧基盤の削除・移行は行わず、通常利用の支障だけを個別Issueで直す。

完了したPhase 2・3の表示・入力・更新契約は[`trip-detail-model.md`](trip-detail-model.md)に保持する。

## 正本と一時Context

このロードマップには最終利用像、Goal、Phase、現在PhaseのStepだけを残す。PhaseやStep途中の比較案、仮判断、レビュー結果は、現在PhaseのGitHub Issue等の一時的な作業単位で扱い、恒久文書へ逐次蓄積しない。

Phase終了時に振り返りを行い、今後も必要な確定事項だけを、このロードマップ、仕様、Decision等の適切な正本へ反映する。その際に後続Phaseと、必要ならGoalも見直す。一時Context専用の恒久文書は作らない。


## Goal 2: 旅程と連動する地図機能を実用完成する

[Issue #159](https://github.com/USXUSX/Calendar/issues/159)によりPhase 1を開始する。
日別地図を基本に、確定地点・候補・将来の経由点を区別し、旅程と地図の予定フォーカスを引き継ぐ。
地図はeffective Tripから導出し、通常予定・日時・訪問順は旅程で編集する。

| Phase | 状態 | 成果・境界 |
| --- | --- | --- |
| 1. 旅程連動地図を表示 | 完了（us完了指示済み） | Google Mapsで日別・全日、Pin詳細、旅程フォーカス連動。実経路線・地点編集なし |
| 2. 地点確認・補正 | 完了（Mac・iPadのus確認済み） | 不足座標の共通補完、位置設定・Pin修正・保存、実機レビュー後の表示調整 |
| 3. 経路表示と経由点 | 未着手・振り返り後に判断 | Google Routes、移動手段別経路、経由点操作と影響区間再計算 |

Phase 1のStepは現行契約確認 → Maps接続・credential境界 → CAL表示モデル →
Frame切替・Pin詳細 → フォーカス連動 → 合成Tripと代表画面の最小確認 → 成果と未確認事項の振り返り。
実装契約は[表示・更新契約](trip-detail-model.md)、接続設定はFrame READMEが所有する。
2026-09-17のus完了指示に基づきPhase 1を完了。Phase 2の[Issue #167](https://github.com/USXUSX/Calendar/issues/167)も、実装・本番反映・公式同期と実機レビュー後の追加修正を経て、2026-09-18のusによるMac・iPad確認完了の申告と完了指示に基づき完了した。Phase 3は未着手とし、完了処理後に停止する。


Phase 1の実装・合成検証・本番反映・実API確認は完了（2026-09-17）。
CAL標準チェック、FrameのHTTP・CAL連携、744×1133 Chromeでのフォーカス／フィルター／既存編集を確認。
usがMaps credentialを保存し本番反映を明示承認した後、公開URLでGoogle地図、日別Pin、Pin詳細、
旅程へのフォーカス付き復帰、全日主要地点を確認した。Google APIのconsole errorはなし。
座標未登録地点は件数表示し、座標補正は行わない。#162ではusの実機レビューを受けて表示を調整し、市場朝食の表示先指定だけを承認済みCAL操作で保存した。
地図保存API・経路providerは追加していない。このPhase 1完了時点ではPhase 2は未着手。現在の作業範囲は#167を参照する。

### Phase 1実用調整（Calendar #162 / Frame #106）

地点集約・対象整理、位置登録済みだけの連番、候補全件と枝番、地点名Pinの衝突優先度、2列一覧、吹き出しの予定内容・通常コメント・開閉、選択範囲とiPad縦配置を完了。中間日の移動拠点は最初の到着順、最終日は帰路の出発順とした。関連test・CI、本番反映・実画面確認・公式同期を完了し、2026-09-17のus完了指示により再確認待ちを解消した。確認結果とPRは[Issue #162](https://github.com/USXUSX/Calendar/issues/162)に記録。この時点ではPhase 2の地点補完は要件記録のみだった。


### Phase 2: 座標補完と位置修正（#167）

取り込み時に地図表示対象の不足座標だけを一度検索し、先頭結果をCALへ保存する。既存座標は保持し、検索失敗でも取り込みを完了する。地図編集では位置を設定・修正・取消できる。既存地点の選択は保存済み座標とGoogle Place IDを利用する。エリア・予定・候補の追加とJSON取込は不足座標の共通補完を利用し、検索失敗時も保存を完了する。
仕様は[座標契約](map-locations.md)。関連Frame Issueは[Frame #114](https://github.com/USXUSX/Frame/issues/114)。地点の表示名、コメントの一括保存、候補Pinの表示優先度、Mac・iPadの操作配置を実機レビューに基づき調整した。2026-09-18、usからMac・iPadとも問題なしとの確認を受け、Phase 2を完了した。Phase 3へは進まない。
