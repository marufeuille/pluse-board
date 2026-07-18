# intervo トレーニングデータ連携 — Story 集

設計は [`intervo-integration-design.md`](./intervo-integration-design.md) を正とする。
本ドキュメントは実装を段階的に切ったストーリー集。上から順に価値が出る順序で並べる。

## 全体像

| # | Story | ねらい | リポ | 依存 | 状態 |
|---|---|---|---|---|---|
| **S0** | PDS 接続・raw 取り込みの疎通 | 個人 PDS の checkin/plan を BigQuery raw に落とす最小疎通 | pluse-board | — | 📄 計画 |
| **S1** | Daily 種目一覧（予定値で先行） | plan の種目/セット/レップで「その日やった内容」を一覧 | pluse-board | S0 | 📄 計画 |
| **S2** | intervo checkin の実績明細化 | checkin の `performed` に種目別 reps/sets を加算（後方互換） | intervo | — | 📄 計画 |
| **S3** | Daily を実績値に切替 | S2 の明細で「スクワット 12×3」を実績表示（予定はフォールバック） | pluse-board | S1, S2 | 📄 計画 |
| **S4** | Weekly レポート | 曜日分布・カテゴリ/種目内訳・頻度・進捗 | pluse-board | S1 | 📄 計画 |
| **S5** | 強度の突合（応用） | Google Health の AZM/心拍を時間窓で突合し強度を補う | pluse-board | S1, S4 | 📄 計画 |
| **S6** | 部位バランス（応用） | 種目→部位マッピングで push/pull/legs 内訳 | pluse-board | S4 | 📄 任意 |

疎結合の契約は AT Protocol lexicon（`dev.marufeuille.workout.plan` / `.checkin`）に限定する。

---

## S0 — PDS 接続・raw 取り込みの疎通

**価値**: intervo の公開出力（PDS）を pluse-board が読めることを確認し、以降の土台にする。

- `ingest/pull_intervo_pds.py` を新規作成。`com.atproto.repo.listRecords` で
  `dev.marufeuille.workout.checkin` と `.plan` を全ページ取得。
- `fitbit_raw.intervo_checkin` / `fitbit_raw.intervo_plan` に `raw`(JSON)+`rkey`+`synced_at` で
  冪等 upsert（既存 `pull_health_api.py` の DELETE→INSERT パターン踏襲）。
- 資格情報を GitHub Secrets 化（`INTERVO_PDS_SERVICE_URL` / `_IDENTIFIER` / `_APP_PASSWORD`、read 専用）。
- `daily.yml` の ingest に best-effort ステップ追加（失敗しても既存 Health API ingest を止めない）。
- **完了条件**: 手動 dispatch で raw 2 テーブルにレコードが入り、件数が PDS と一致する。

## S1 — Daily 種目一覧（予定値で先行）

**価値**: 要件① を最短で満たす。S2 完了前は plan の**予定**セット/レップで表示。

- `stg_intervo_plan`（`plan.exercises[]` を 1 種目 1 行に unnest）。
- `stg_intervo_checkin`（session 属性）。
- `mart_training_daily`（日 × 種目、`is_planned=TRUE`）と `mart_training_session`。
- Evidence `reports/pages/training.md` に「日付選択 → その日の種目テーブル」。予定バッジを付ける。
- **完了条件**: ある日を選ぶと「スクワット 3 セット × 12 回（予定）」等が並ぶ。

## S2 — intervo checkin の実績明細化（intervo リポ）

**価値**: 予定ではなく**実績**の粒度（実際に何回やったか）を PDS に出す。

- `WorkoutPdsRecordMapper.mapCheckin` の `performed` に `exercises[]`
  （種目別 `sets`/`reps[]`/`totalReps`/`durationSeconds[]`）を加算。`setCount` 等は残す。
- `WorkoutPdsRecordMapperTest` にケース追加。心拍は引き続き非送信。
- リリースノート（`docs/release-notes-<VERSION>.md`）を用意しタグ運用。
- **完了条件**: 新規 checkin の `performed.exercises` に種目別実績が入る。旧 reader は無視できる。

## S3 — Daily を実績値に切替

**価値**: 「スクワット 12×3」を**実績**で表示（S2 未反映の旧レコードは予定へフォールバック）。

- `stg_intervo_checkin_exercise`（`performed.exercises` を unnest、無ければ plan にフォールバックし
  `is_planned` を立てる）。
- `mart_training_daily` を実績優先に変更。Evidence で予定/実績を色分け。
- **完了条件**: 明細ありは実績、なしは予定と一目で分かる。

## S4 — Weekly レポート

**価値**: 要件②。設計の「標準的な表現」に沿った週次サマリ。

- `mart_training_weekly`（`WEEK(SUNDAY)`、欠週 0 埋め）。曜日分布・カテゴリ/種目内訳・
  セッション数/トレーニング日数・前週比。
- Evidence に週選択 UI・曜日ヒートマップ・積み上げ棒・サマリ BigValue。
- `about.md` に週次指標の定義（ボリューム＝セット×レップ、強度は代理指標、tonnage/RPE 非対応）を追記。
- **完了条件**: 週を選ぶと「火・木・土に実施、筋トレ内訳〜、総レップ〜、前週比〜」が出る。

## S5 — 強度の突合（応用）

**価値**: intervo に無い「強度」を Google Health の AZM/心拍で補う。

- intervo セッションと `stg_exercise`（`STRENGTH_TRAINING`）を completedAt/開始終了の時間窓で突合し
  `mart_training_session_enriched`。ACWR（既存 `mart_acwr`）と併記。
- 突合の許容誤差・重複排除ルールを `about.md` に定義。
- **完了条件**: セッション詳細に「種目明細（intervo）＋ AZM/心拍（Google Health）」が並ぶ。

## S6 — 部位バランス（任意）

- 種目名→部位（push/pull/legs 等）のマッピング表を pluse-board 側に持ち、週次の部位内訳を出す。
- intervo の内部仕様には依存しない（種目名/`exerciseType` のみ使用）。

---

## bd / Shortcut への取り込み

pluse-board は `bd`（beads）で課題管理する方針（`AGENTS.md`）。本 Story 集は
epic 1 + 子タスク（S0〜S6）として `bd` に登録できる。Shortcut 側 sc-27 は本 epic の親として残す。
登録の要否はユーザー確認事項（設計ドキュメント末尾「未確定事項」参照）。
