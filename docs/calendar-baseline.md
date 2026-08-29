# CAL再構築Baseline

## 1. 位置付け

この文書はIssue #46で確定した、CALの責務、主要Entity、データの役割分担、他ツールとの境界を定める現行Baselineである。後続のschema、interface、UI、移行はこのBaselineを前提に個別Issueで決定する。

既存のformal Trip JSON、生成手順、Schema、stable ID、cross-reference validationは、Tripの完全旅程表現とAI再生成方式として新Baselineにも維持し、原則として再利用対象とする。既存のread-only旅程Webは現行実装を理解するために残すが、CAL全体のアプリケーションBaselineではない。旧実装や実データは、このIssueでは変更、移行、削除しない。

## 2. CALの責務

CALは、個人の時間、予定、行うべきことを管理するドメイン基盤である。主要Entityを次の3つとする。

- `Trip`: 旅行というまとまり。期間、参加者、旅行に属する予定等を束ねる。
- `Event`: 日時を持つ予定。旅行中の予定に限らず、通常のスケジュールも表す。
- `Todo`: 人が行うべきこと。必要に応じて`Trip`または`Event`へ関連付けられる。

CAL全体では`Trip`に属する予定と通常の予定を`Event`として関係付けられる。一方、各旅行の旅程機能では、曖昧さ、不完全さ、情報粒度の違いをAIが整理したformal Trip JSONを、現在の完全な旅程表現として扱う。Trip JSON内の旅程項目とCALの`Event`をどのように同期または参照するかは後続Issueで決定し、このBaselineでは二重管理方式を固定しない。

CALのドメイン用語には`Task`を使用しない。人が行うべきことは`Todo`と呼ぶ。旧JSON schema、サンプル、プロトタイプ実装に残る`tasks`は旧Baselineの互換対象としてのみ扱い、新しいCALモデルへ引き継がない。`Task / TSK`はMac上のJob実行ツールを指し、TSK内の実行単位は`Job`とする。

## 3. ツール間の責務境界

| 対象 | 責務 | CALとの境界 |
| --- | --- | --- |
| CAL | `Trip / Event / Todo`と、それらの関係・状態遷移を管理する | 実データを保持し、意味ベースのread/write境界を提供する |
| FRM | owner向けWeb入口を提供する | CALの物理SQLite schemaを直接操作せず、CALの意味ベースの境界を利用する |
| TSK | Mac上で`Job`を実行するscheduler | CAL全体を同期しない。自動処理が必要な`Event`または`Todo`だけを、将来の明示的な連携境界から`Job`へ接続する |
| ENT | 複数用途で使う取得・蓄積データの基盤 | CALとDBを統合しない。ENTの取得情報をCALへ変換することはできるが、CALデータをENTへ集約することは前提にしない |

FRMのowner向け画面は将来`Today / Schedule / Trips / Todos`を扱える。framework、API方式、CLI、library、local APIの選択はこのBaselineでは固定しない。

## 4. SQLiteとTrip JSONの役割分担

CALはSQLiteとformal Trip JSONのハイブリッド構成を前提とする。どちらも`/Users/us/Tools/LocalData/Calendar_Local`内に置き、Gitや共有参考資料へ実データを置かない。

SQLiteは構造化されたCALの状態を管理する。第一候補の配置先は`/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3`とし、主に次を扱う。

- CAL全体のTrip管理情報
- 通常の`Event`と`Todo`
- `Trip / Event / Todo`間の関係
- `AI Instruction`
- `Direct Override`
- share、visibility等の状態
- その他の構造化されたCAL横断状態

formal Trip JSONは各旅行の現在の完全旅程を表す。単なるimport/export用交換形式ではなく、AIが旅程全体を解釈し、生成・再生成するためのauthoritativeな完全表現である。既存のJSON Schema、stable ID、cross-reference validationを原則として再利用対象とする。AI生成、import/export、外部連携にも同じformal JSONを利用できる。

SQLite schema、Trip JSONとの同期・参照方式、配置規則、更新のatomicity、履歴・rollbackは後続Issueで決定する。このIssueではDBや新しいデータ経路を実装しない。

3層の役割は維持する。

- `Calendar_Dev`: コード、確定仕様、schema、test、Issue、PR
- `Calendar_GD`: Review、Screenshot、共有参考資料
- `Calendar_Local`: SQLite、formal Trip JSONを含む実データ、runtime data、machine-local data

## 5. 旅程変更の入力経路

旅程の曖昧さや複数箇所に及ぶ調整はAIに交通整理させ、常に次版の完全Trip JSONを生成する。再生成には、現在のTrip JSONに加えて次の2系統の入力を渡す。

### AI Instruction

ユーザーが自然言語で登録する変更意図。AIが次回再生成時に解釈し、旅程全体へ反映する。「2日目は移動を少なくする」「雨天時の候補を追加する」等、解釈や全体調整を必要とする入力を扱う。

### Direct Override

ユーザーが旅程画面上で登録する具体的な変更。コメント、メモ、店名、時刻等の明示値を扱う。Direct Overrideは現在のJSONへ一度適用して消費する入力ではない。次回以降のAI再生成にも渡し、ユーザーが直接指定した内容が失われないようにする。解除、競合、適用済み状態等のライフサイクルは後続Issueで決定する。

初期Baselineではhard/soft等へ細分化せず、`AI Instruction`と`Direct Override`を区別する。

```text
現在のTrip JSON + AI Instructions + Direct Overrides
  -> AI
  -> 新しい完全Trip JSON
```

## 6. ownerデータとparticipant向けread model

CALのSQLite、Trip JSON、owner向けドメイン境界は、ownerの完全なデータを扱う。旅行参加者へCAL本体、SQLite、owner用Trip JSON、owner向けread/write境界を直接公開しない。

participant向け共有は、ownerデータから共有対象だけを抽出したread modelを生成する境界で行う。

- 初期visibilityは`owner`と`participants`を基本とする。
- 主な共有対象は`Trip`と`Event`とする。
- `Todo`は初期の必須共有対象にしないが、将来の明示的な共有を妨げない。
- participant向けread modelは読み取り専用で、owner専用フィールドや未共有Entityを含めない。
- owner側の更新後にread modelを再生成できる一方向の派生物とし、participant側の値を正本へ逆流させない。
- 共有対象の選択規則、URL、認証、公開基盤、更新頻度は後続Issueで確定する。

この境界は将来の共有を可能にするための仕様であり、このIssueでは外部公開を開始しない。

## 7. 旧Baselineとの関係

### Supersedeする内容

- Calendar自身のread-only旅程WebをCALの中心とする方針
- 旅程管理だけをCAL全体の主目的とする方針
- 旅行JSONだけでCAL全体の`Trip / Event / Todo`と横断状態を管理する方針
- 旅行を中心に`Day / ScheduleItem / Transport / Preparation`等からCAL全体を構成する前提

### 残す内容

- 各旅行をformalな完全Trip JSONで表す基本方式
- AIが現在のTrip JSONと変更入力から次版の完全Trip JSONを再生成する方式
- JSON Schema、stable ID、cross-reference validation、予定と実績を分ける考え方
- 既存のSchema、validator、合成サンプル、旅行JSON生成・運用文書は、再利用対象かつ現行実装の記録として残す。
- read-only Webの実装は移行・再利用判断の資料として残す。
- 既存旅程データと旧実装は、新Baselineへの移行または再利用を決める後続Issueまで変更しない。

旧資料にある個別の表示仕様や旅行詳細項目は、自動的に新Baselineへ継承しない。後続Issueで採用したものだけを新しい確定仕様へ昇格する。

## 8. 後続Issueへの分割

1. `Trip / Event / Todo`のSQLite schema、状態遷移、参照制約
2. SQLiteとformal Trip JSONの同期・参照・atomic update・履歴方式
3. `AI Instruction / Direct Override`のschema、ライフサイクル、競合・解除規則
4. CALが提供する意味ベースのdomain interfaceと、FRMから利用するread/write方式
5. 既存Trip JSON、Schema、validatorの再利用範囲と必要な非破壊的移行
6. FRM owner向け`Today / Schedule / Trips / Todos` read modelと画面
7. FRMからCALを更新するcommand境界、競合、validation
8. formal Trip JSONを表示・変更するowner向け旅行UI
9. participant向けread modelの投影規則、共有範囲、認証、公開基盤
10. Reminder、繰返し`Event`、AI更新、必要箇所だけのTSK `Job`連携
11. ENT取得データをCALへ変換する連携契約
12. 旧read-only prototypeの再利用判断と非破壊的整理

各Issueは、このBaselineで未確定とした方式を必要な範囲だけDecision化し、実装、移行、公開を混在させない。
