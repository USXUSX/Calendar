# Calendar

CALは個人の予定・Todo・旅程を扱うdomain基盤です。通常のWeb表示・操作はFrameが担当し、正式Trip JSONとSQLiteの更新・ValidationはCALが所有します。

## 現在の利用経路

- Chatの新規・既存Trip更新は既存RDCから[CAL専用コマンド](docs/chat-schedule.md)を呼び、CALで検証・正式保存してreceiptを受け取る。Frameの手動JSON取込も保持する。
- 既存TripはFrameで直接編集・予定追加／削除／並び替え・候補選択ができる。CALの編集を微修正には限定しない。
- 継続編集は専用コマンドからeffective Trip・revision・未処理指示を取得して更新する。context自動共有・candidate自動採用は停止し、残存ファイルを削除しない。
- 候補探索・比較・大きな旅程編集・調査コメントはChatで行う。通常UIには旧Working／AI生成・候補検索／AFM推薦・コメントAIを置かない。Place補完と天気はCALの意味境界を使う。

新規登録と既存Trip更新を区別し、通常予定と旅程のデータ形式は別に保ちます。生成・受渡しは[生成ガイド](docs/trip-json-generation.md)、新規採用は[JSON取込契約](docs/trip-json-import.md)、日常操作は[運用入口](docs/operation.md)を参照してください。

## 予定画面の直接操作

Frame #177 Phase 2の月間・一覧・複数月と通常Event/Todo操作は[期間表示・保存契約](docs/schedule.md)を使う。Eventの任意TripリンクとTodoメモを追加し、既存DBには明示した追加migrationを適用する。通常予定・Todoは既存RDCから[正式Chatコマンド](docs/chat-schedule.md)でも保存・結果照合できる。定期予定・タスクの条件は同CLIから設定し、各回を期間表示・単回操作できる。Google反映は[専用一方向連携](docs/google-calendar.md)を使う。

独立した旅行の先行管理・旅程接続・Event/Todoのcategory/旅行関連/メール参照は[日程契約](docs/schedule.md#独立した旅行管理221)を使います。既存DBは明示したtravel migrationが必要です。

## 現在地

2026-09-16、usの基本検証完了の申告と全体完了指示に基づき、Goal 1／Phase 8を一旦完了し、実利用・保守へ移行します。Chat生成JSON取込、直接編集、継続Chat往復、候補操作、Place補完・天気を現行の利用範囲とします。

完了記録と確認範囲は[Issue #96](https://github.com/USXUSX/Calendar/issues/96)、今後の保留事項は[ロードマップ](docs/development-roadmap.md)を参照してください。全面再構築は行わず、実利用で支障が出た箇所だけ対応します。

Goal 2と新Goal 3を[Calendar #174](https://github.com/USXUSX/Calendar/issues/174)で完了しました（2026-09-18）。地図・位置補正に加え、明示した車区間の実経路と鉄道のGoogle Maps経路検索リンクを表示できます。新規Chat生成は地点情報を可能な範囲で充実し、地図で観光地点を選ぶと取得可能な公式画像を1枚表示します。画像がない場合は非表示です。

Mac・iPad相当幅の公開画面、車の実経路と公式画像の実取得を確認し、本番反映・公式同期を完了しました。今回の物理iPad操作は未実施です。Goal 1の完了判断を維持し、ここでCAL開発を一区切りとします。次Goalへは進まず、実利用で必要な保守を行います。

## 責務と保持基盤

正式complete Trip JSONはCALが最後に採用した基礎データ、SQLiteは構造化状態とDirect Overrideを管理します。表示するeffective Tripは両者を合成します。呼出側は`Sources/calendar_domain/`の意味APIへDB・Trip rootを明示し、テーブルや正式JSONの配置を直接扱いません。
[Baseline](docs/calendar-baseline.md)、[表示・更新契約](docs/trip-detail-model.md)、[直接操作](docs/direct-schedule.md)、[Place取得・採用](docs/place-acquisition.md)が各契約の正本です。

旧read-only Web、Working保存・再生成、AI Instruction Patch／one-shot workerの実装は保持しています。通常のChat往復とは別経路であり、その追加開発や有効化はGoal 1の完成条件ではありません。WorkingのValidation・stale・atomic adoption・診断・candidate preview契約は[表示・更新契約](docs/trip-detail-model.md)を参照してください。

## Three layers

| Role | Location | Authority |
| --- | --- | --- |
| Development | `/Users/us/Tools/Development/Calendar_Dev` | Git-managed source, confirmed specifications, tests, Issues, and PRs |
| Shared references | `/Users/us/マイドライブ/Tools/Calendar_GD` | One-way reference copy of committed Git source |
| Private local data | `/Users/us/Tools/LocalData/Calendar_Local` | Non-shared inputs, runtime data, caches, and temporary data |

## Repository map

- `AGENTS.md`: durable Codex rules and discovery order
- `docs/project-structure.md`: boundaries and information flow
- `docs/workflow.md`: current TDS entry and Calendar reference-copy handling
- `docs/decisions.md`: confirmed architectural decisions
- `docs/calendar-baseline.md`: current confirmed CAL responsibilities and data baseline
- `docs/initial-release.md`: Goal 1 scope, Chat paste format, and external data acquisition / retention policy
- `docs/development-roadmap.md`: CAL's final usage vision and current Goal / Phase / Step roadmap
- `docs/calendar-specification.md`: retained Trip JSON specification subject to scoped reuse
- `docs/trip-detail-ui.md`: confirmed iPad mini / iPad itinerary-detail UI requirements
- `docs/trip-detail-model.md`: current UI display derivation and semantic update boundaries
- `Schemas/trip.schema.json`: current formal Trip JSON contract and reuse baseline
- `Schemas/calendar-v3.sql`: current reproducible SQLite schema, including Working Trip state
- `Schemas/calendar-v2.sql`: retained schema revision for Trip versions and generation requests
- `Schemas/calendar-v1.sql`: retained initial SQLite schema revision
- `docs/trip-json-generation.md`: current new-Trip complete-JSON generation and candidate handoff
- `docs/map-locations.md`: JSON取り込みの座標補完と地図上の位置保存
- `docs/operation.md`: current Frame operation and retained legacy entry points
- `Sources/`: CAL semantic domain and retained read-only Web prototype
- `Tests/`: automated tests and test guidance
- `Samples/`: synthetic, non-sensitive examples safe to commit

## 開発とValidation

作業は`AGENTS.md`と現行GitHub TDSから開始します。合成データを使う標準チェックはリポジトリ直下で実行します。

```sh
sh Tests/run.sh
```

空の開発DB作成とcomplete JSONの確認は、対象pathを明示します。initializerは空でない対象を拒否します。

```sh
python3 scripts/init_calendar_db.py /path/to/new/calendar.sqlite3
python3 scripts/validate_trip.py /path/to/trip.json
```

通常testは実API・credential・課金を必要としません。実運用切替、実Trip操作、物理端末受入は技術確認と分けて扱います。
