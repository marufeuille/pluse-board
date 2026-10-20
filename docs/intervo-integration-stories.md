# intervo トレーニングデータ連携 — Story 集

> **改訂 (sc-27 レビュー反映)**: AT Protocol / PDS 経由は撤回し、連携ハブを **Health Connect** に
> 置き直した（intervo issue [#11](https://github.com/marufeuille/intervo/issues/11) の方針）。

設計は [`intervo-integration-design.md`](./intervo-integration-design.md) を正とする。
本ドキュメントは実装を段階的に切ったストーリー集。上から順に価値が出る順序で並べる。

## 全体像

| # | Story | ねらい | リポ | 依存 | 状態 |
|---|---|---|---|---|---|
| **S0** | Google Health API のセグメント露出を検証 | 既存 ingest だけで種目/回数が取れるか（経路1可否）を実データで確認 | pluse-board | — | 📄 計画 |
| **S1** | intervo の HC 書き込みにセット粒度を加算 | `ExerciseSessionRecord` に segments/reps を付与（後方互換） | intervo | — | 📄 計画 |
| **S2a** | 経路1: 既存 raw を拡張して取り込み | Google Health API が露出するなら `stg_exercise` を拡張 | pluse-board | S0, S1 | 📄 条件付き |
| **S2b** | 経路2: Health Connect → BQ forwarder | 露出しないなら HC を直接読む forwarder を別 repo で（#11） | 別 repo | S1 | 📄 条件付き |
| **S3** | Daily 種目一覧 | 「スクワット 12×3」を Daily で一覧 | pluse-board | S2a or S2b | 📄 計画 |
| **S4** | Weekly レポート | 曜日分布・カテゴリ/種目内訳・頻度・進捗 | pluse-board | S3 | 📄 計画 |
| **S5** | 強度の突合（応用） | Google Health の AZM/心拍を時間窓で突合し強度を補う | pluse-board | S3, S4 | 📄 任意 |
| **S6** | 部位バランス（応用） | 種目→部位マッピングで push/pull/legs 内訳 | pluse-board | S4 | 📄 任意 |

疎結合の契約は **Health Connect のデータモデル**に限定する（intervo の内部 DB/非公開 API に非依存）。

---

## S0 — Google Health API のセグメント露出を検証

**価値**: 一番安い経路1が使えるかを最初に確定させ、S2a/S2b の分岐を決める。

- 実データで `fitbit_raw.exercise` の JSON に `segment` / `repetitions` 相当が含まれるか確認する。
  含まれるなら経路1（既存 ingest 拡張）で完結。含まれないなら経路2（forwarder）へ。
- **完了条件**: 「Google Health API v4 は HC のセグメント/回数を露出する/しない」が結論づく。

## S1 — intervo の HC 書き込みにセット粒度を加算（intervo リポ）

**価値**: 要件を満たす唯一の必須改修。既存の HC 書き込みに**セット粒度を加算**（後方互換）。

- `HealthConnectWriter.write` の `ExerciseSessionRecord` に `segments: List<ExerciseSegment>` を付与。
  `performedSetsJson`（既に companion にあるセット単位実績）を素材に、セット/種目を
  `startTime`/`endTime`/`repetitions` で表現。既知種目は `EXERCISE_SEGMENT_TYPE_*` へマッピング。
- **種目名の保持方針を決める**: (a) `notes` に構造化サマリ併記 / (b) 種目名→型マッピングを下流に持つ。
- 任意: 予定を `PlannedExerciseSessionRecord` で書き「予定 vs 実績」に対応。
- テスト追加。心拍は従来どおり `HeartRateRecord`。
- **完了条件**: 新規セッションに segments/reps が入り、旧レコードは session 単位で従来どおり読める。

## S2a — 経路1: 既存 raw を拡張して取り込み（S0 が肯定なら）

- `stg_exercise` を拡張し、JSON の segment/repetitions を種目/セット行へ展開。
- `data_origin` 相当で intervo 由来を識別し、既存 `mart_strength_*` との二重計上を避ける。
- **完了条件**: 既存 ingest のみで種目/セットが staging に出る。

## S2b — 経路2: Health Connect → BQ forwarder（S0 が否定なら・別 repo）

**価値**: intervo issue #11 の実体。HC を直接読み BigQuery raw へ着地。

- 独立 forwarder（HC read + WorkManager + `getChanges`）。`fitbit_raw.hc_exercise_session`
  （`raw`+`data_origin`+`record_id`+`client_record_id`+`last_modified_time`）へ冪等 MERGE、
  削除（tombstone）も転送。
- HC READ 権限（`READ_HEALTH_DATA_HISTORY` / `READ_HEALTH_DATA_IN_BACKGROUND`）・Play 審査に対応。
- intervo 専用にせず汎用 ELT にし、`dataOrigin.packageName` で intervo を絞る。
- **完了条件**: HC の intervo セッション（+segments）が raw に着地し件数一致。

## S3 — Daily 種目一覧

**価値**: 要件①。日付選択 → その日の種目テーブル（種目名・セット×レップ・時間）。

- `stg_training_session` / `stg_training_set` → `mart_training_daily` / `mart_training_session`。
- Evidence `reports/pages/training.md` に Daily 一覧。予定を書く場合は予定/実績を色分け。
- **完了条件**: ある日を選ぶと「スクワット 3 セット × 12 回」等が並ぶ。

## S4 — Weekly レポート

**価値**: 要件②。設計の「標準的な表現」に沿った週次サマリ。

- `mart_training_weekly`（`WEEK(SUNDAY)`、欠週 0 埋め）。曜日分布・カテゴリ/種目内訳・
  セッション数/トレーニング日数・前週比。
- Evidence に週選択 UI・曜日ヒートマップ・積み上げ棒・サマリ BigValue。
- `about.md` に週次指標の定義（ボリューム＝セット×レップ、強度は代理指標、tonnage/RPE 非対応）を追記。
- **完了条件**: 週を選ぶと「火・木・土に実施、筋トレ内訳〜、総レップ〜、前週比〜」が出る。

## S5 — 強度の突合（応用）

- intervo セッションと `stg_exercise`（`STRENGTH_TRAINING`）を時間窓で突合し
  `mart_training_session_enriched`（種目明細＋AZM/心拍）。ACWR（既存 `mart_acwr`）と併記。
- 突合の許容誤差・重複排除ルールを `about.md` に定義。

## S6 — 部位バランス（任意）

- 種目名→部位（push/pull/legs 等）のマッピング表を下流に持ち、週次の部位内訳を出す。
  intervo の内部仕様には依存しない（種目名/型のみ使用）。

---

## bd / Shortcut への取り込み

pluse-board は `bd`（beads）で課題管理する方針（`AGENTS.md`）。本設計のレビュー確定後、
**Shortcut に別ストーリー**として起こす（ユーザー方針）。必要なら `bd` にも epic + 子タスク（S0〜S6）を登録する。
