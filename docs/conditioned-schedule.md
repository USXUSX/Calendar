# 条件指定による新規予定追加（Calendar #91）

CALの意味境界で検索、AFMの最大3推薦、明示選択による予定1件追加までを扱う。
owner画面はBaselineどおりFrameの責務。Frame画面への接続・実機操作は未実施。
Calendarのlegacy read-only Webは変更しない。

## 呼出し

```python
from Sources.place_acquisition import WikidataAdapter, FacilityQuery
from Sources.aig_candidate_recommendation import command_transport

adapter = WikidataAdapter()  # 対話callerが再利用する
transport = command_transport("/explicit/path/aig-candidate-recommendation")
result = calendar.search_schedule_candidates(
    trip_id, day_id, "青町で静かな席のあるカフェ", adapter, transport,
    search_queries=[FacilityQuery("カフェ", "青町"), FacilityQuery("喫茶店", "青町")])
# result.candidatesを順序どおり表示。reason/unverified_conditionsは助言である。
saved = calendar.add_conditioned_schedule(
    command_id, trip_id, day_id,
    {"title": "休憩", "category": "food", "start": "14:00", "end": "15:00"},
    result, [result["candidates"][0]["id"]], confirmed=True)
queries = calendar.list_unresolved_schedule_queries(trip_id)
```

`query`はusの元の自然文（非空・最大500文字）を空白も含め保持する。
任意の`search_queries`は呼出側の検索戦略が用意する1〜3個の`FacilityQuery`であり、元条件と独立する。
未指定時は元条件と日の代表エリアを使う。検索語の最終最適化は対象外で、
Wikidataのlabel/alias検索が自然文や飲食店を網羅する保証はない。候補なしを許容する。
同じadapterを直列利用し、検索失敗時は後続queryを中止する。既存adapterの負荷・cooldownを維持する。
候補を集約・完全一致重複除去して最大10件で打ち切り、元条件と候補根拠をAIGへ1回だけ渡す。
Trip全体、参加者、予約、CAL identityを外部へ渡さない。地域hintを施設の地域という事実に転用しない。

AIG契約の正本は[AI-Gateway mainのREADME](https://github.com/USXUSX/AI-Gateway/blob/main/README.md#afm-candidate-recommendation-boundary-issue-13)。
`aig.candidate-recommendation.v1`を使用し、CLIは`--provider afm`を固定する。
返却schema・候補所属・重複・上限を再検証し、不正結果を切詰めて成功にしない。
推薦順を変更せず、理由と未確認条件を一時表示へ返す。正式な条件適合Validationには使わない。
OpenAI、routing、retry、AFMによる検索を追加しない。

結果の`status`は`recommendations / no_candidates / search_failed / recommendation_failed`。
失敗時にも元条件を保持し、選択なしで追加できる。取得や推薦は書込みを行わない。

## 選択と保存

内部callerが未変更の`result`を操作中だけ保持する。画面から受け取るのは候補IDと確認操作であり、
画面が返した任意のJSONを取得結果として信用しない。再検索時は古い結果を置換する。
候補の`fields`だけがadapterの保存許諾・CALの型検証を通った値。
`context`、snippet、provider ID、AFM理由・未確認条件は正式保存しない。
保存可能な名称がない候補は`selectable=false`で表示し、正式Placeとして採用できない。

- 1 ID：そのPlaceだけを`candidatePlaceIds`と`selection`へ入れる。
- 2〜3 ID：選んだPlaceを`candidatePlaceIds`へ入れ、`selection=[]`とする。
- 0 ID：両配列を空にし、架空のPlaceを作らない。

全ての場合で予定は1件だけ。その予定の任意field `searchQuery`が元条件の正本となる。
Schemaは空の`candidatePlaceIds`を許可するが、その場合はsemantic Validationで非空（空白のみも不可）の`searchQuery`を必須とする。
候補がある既存JSONには新fieldを必須追加せず、移行は不要。
予定状態は既存取込と同じ`undecided`で、場所確定は`selection`で区別する。
カテゴリはcallerの明示した`sightseeing / food / accommodation`を必須とし推測しない。
時刻は省略時に未定。終了だけ、逆転時刻、不正時刻は確認・補正へ返す。

日末へorderを付けて追加し、他予定や移動のorder・時刻を変えない。
同じ日の同時刻（両方未定も含む）で内容が正規化一致、または選択済み施設のURL・座標等が一致する
明白な重複はConflictとする。同名だけで施設を同一視しない。同じcommand_idの再送も追加しない。
検索後に対象日の代表エリアが変われば再検索を要求し、他予定の編集は現行effective Tripから保持する。

## Direct Overrideの追加境界

通常局所変更として、既存SQLiteのDirect Overrideへ1 transactionで保存する。
集合全体のsnapshotで他予定を固定しないため、CAL内部で次のstable ID指定を追加する。

- Trip targetの`/places/@<place-id>`：その1 Place。
- Day targetの`/scheduleItems/@<item-id>`：その1 ScheduleItem。

これはCAL内部のmember指定であり、外部JSON Patchのpathではない。
Place → ScheduleItem → 通常field Overrideの順に合成する。
同じIDがbaseにあれば当該memberだけを指定値へ置換し、なければ追加するため重複しない。
別collectionとのID衝突は拒否する。新規memberも後から通常の手動編集・Place補完を利用できる。
明示値は通常Override同様に再生成後も保持され、candidateとの合成結果もSchema/semantic検証する。

保存前にwriter lockを取り、未完了adoption journalがあればConflictとする。
Place群と予定を全てSchema/semantic検証してから保存し、途中失敗は全てrollbackする。
formal Trip JSON、Working行、generation stateを変更しない。Workingは既存のrevision比較でstaleになる。

`list_unresolved_schedule_queries`はselectionが空の予定の元条件、stable target、内容、カテゴリ、候補IDを返す。
通常詳細viewも`search_query`を返し、既存Working exportのeffective Tripからも参照できる。
後続AIを起動するworkflow・定期再検索・既存予定への候補追加（#92）は追加しない。

通常Validationは合成候補、mock AIG、temporary DBで実施する。
AFM実行品質・live検索品質・Frame表示・実機・productionはこのValidationでは確認しない。
