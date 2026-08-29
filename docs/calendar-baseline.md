# CAL再構築Baseline

## 1. 位置付け

この文書はIssue #46で確定した、CALの責務、主要Entity、データ正本、他ツールとの境界を定める現行Baselineである。後続のschema、interface、UI、移行はこのBaselineを前提に個別Issueで決定する。

既存の旅行JSON仕様、生成手順、read-only旅程Webは、現行実装を理解し、再利用または一回限りの移行を検討するために残す。ただし、それらはCAL全体の現行Baselineでも、再構築後の実データ契約でもない。旧実装や実データは、このIssueでは変更、移行、削除しない。

## 2. CALの責務

CALは、個人の時間、予定、行うべきことを管理するドメイン基盤である。主要Entityを次の3つとする。

- `Trip`: 旅行というまとまり。期間、参加者、旅行に属する予定等を束ねる。
- `Event`: 日時を持つ予定。旅行中の予定に限らず、通常のスケジュールも表す。
- `Todo`: 人が行うべきこと。必要に応じて`Trip`または`Event`へ関連付けられる。

旅程は独立した正本データ列ではなく、原則として`Trip`に属する`Event`を時系列表示したread modelとする。旅行固有の詳細Entityや値オブジェクトは今後追加できるが、`Trip / Event / Todo`の責務を重複させない。

CALのドメイン用語には`Task`を使用しない。人が行うべきことは`Todo`と呼ぶ。旧JSON schema、サンプル、プロトタイプ実装に残る`tasks`は旧Baselineの互換対象としてのみ扱い、新しいCALモデルへ引き継がない。`Task / TSK`はMac上のJob実行ツールを指し、TSK内の実行単位は`Job`とする。

## 3. ツール間の責務境界

| 対象 | 責務 | CALとの境界 |
| --- | --- | --- |
| CAL | `Trip / Event / Todo`と、それらの関係・状態遷移を管理する | 実データを保持し、意味ベースのread/write境界を提供する |
| FRM | owner向けWeb入口を提供する | CALの物理SQLite schemaを直接操作せず、CALの意味ベースの境界を利用する |
| TSK | Mac上で`Job`を実行するscheduler | CAL全体を同期しない。自動処理が必要な`Event`または`Todo`だけを、将来の明示的な連携境界から`Job`へ接続する |
| ENT | 複数用途で使う取得・蓄積データの基盤 | CALとDBを統合しない。ENTの取得情報をCALへ変換することはできるが、CALデータをENTへ集約することは前提にしない |

FRMのowner向け画面は将来`Today / Schedule / Trips / Todos`を扱える。framework、API方式、CLI、library、local APIの選択はこのBaselineでは固定しない。

## 4. データ正本と交換形式

実データの正本は`/Users/us/Tools/LocalData/Calendar_Local`内のSQLiteとし、第一候補の配置先を`/Users/us/Tools/LocalData/Calendar_Local/db/calendar.sqlite3`とする。SQLite schema、アクセス方式、バックアップ、移行手順は後続Issueで決定する。このIssueではDBを作成しない。

3層の役割は維持する。

- `Calendar_Dev`: コード、確定仕様、schema、test、Issue、PR
- `Calendar_GD`: Review、Screenshot、共有参考資料
- `Calendar_Local`: SQLiteを含む実データ、runtime data、machine-local data

JSONは正本ではない。AI生成、import/export、外部連携、一時的な検証、合成サンプル等の交換形式として使用できる。交換JSONのschemaとSQLiteの写像は、用途ごとに後続Issueで定める。交換JSONを配置または生成しても、明示的なimportを経ずに正本とはならない。

## 5. ownerデータとparticipant向けread model

CALのSQLiteとowner向けドメイン境界は、ownerの完全なデータを扱う。旅行参加者へCAL本体、SQLite、owner向けread/write境界を直接公開しない。

participant向け共有は、ownerデータから共有対象だけを抽出したread modelを生成する境界で行う。

- 初期visibilityは`owner`と`participants`を基本とする。
- 主な共有対象は`Trip`と`Event`とする。
- `Todo`は初期の必須共有対象にしないが、将来の明示的な共有を妨げない。
- participant向けread modelは読み取り専用で、owner専用フィールドや未共有Entityを含めない。
- owner側の更新後にread modelを再生成できる一方向の派生物とし、participant側の値を正本へ逆流させない。
- 共有対象の選択規則、URL、認証、公開基盤、更新頻度は後続Issueで確定する。

この境界は将来の共有を可能にするための仕様であり、このIssueでは外部公開を開始しない。

## 6. 旧Baselineとの関係

### Supersedeする内容

- `Calendar_Local/trips/<trip-id>.json`の「1 Trip = 1 JSON」を実データ正本とする方針
- 正式な完全旅行JSONをCAL全体の機械可読データ契約とする方針
- Calendar自身のread-only旅程WebをCALの中心とする方針
- 旅程の閲覧とAIによる完全JSON再生成をCAL全体の主目的・主要更新経路とする方針
- 旅行を中心に`Day / ScheduleItem / Transport / Preparation`等からCAL全体を構成する前提

### 残す内容

- 安定ID、参照整合性、予定と実績を分ける考え方等は、後続schema設計で再評価できる。
- 既存のSchema、validator、合成サンプル、read-only Web、旅行JSON生成・運用文書は、現行実装の記録と移行元資料として残す。
- 既存旅程データと旧実装は、新Baselineへの移行または再利用を決める後続Issueまで変更しない。

旧資料にある個別の表示仕様や旅行詳細項目は、自動的に新Baselineへ継承しない。後続Issueで採用したものだけを新しい確定仕様へ昇格する。

## 7. 後続Issueへの分割

1. `Trip / Event / Todo`のSQLite schema、状態遷移、参照制約
2. CALが提供する意味ベースのdomain interfaceと、FRMから利用するread/write方式
3. 既存旅行JSONからSQLiteへの一回限りの移行・検証・rollback方針
4. FRM owner向け`Today / Schedule / Trips / Todos` read modelと画面
5. FRMからCALを更新するcommand境界、競合、validation
6. `Trip`に属する`Event`から旅程を構成するowner向け旅行UI
7. participant向けread modelの投影規則、共有範囲、認証、公開基盤
8. Reminder、繰返し`Event`、AI import/update、必要箇所だけのTSK `Job`連携
9. ENT取得データをCALへ変換する連携契約
10. 旧prototype、Schema、validator、運用文書の再利用判断と非破壊的整理

各Issueは、このBaselineで未確定とした方式を必要な範囲だけDecision化し、実装、移行、公開を混在させない。
