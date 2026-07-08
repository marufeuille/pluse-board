# Dataplex ガバナンス学習 — 検証ストーリー集

## Context

OpenLineage の Phase 0–2（[`openlineage-dataplex-design.md`](openlineage-dataplex-design.md)）で、
`Health API → fitbit_raw → fitbit_staging → fitbit_mart` の **リネージ（辺）** を Dataplex（Knowledge Catalog）上に
地続きで可視化できた。本ドキュメントはその続きとして、**同じ Dataplex 上の別サブシステム**である
**データ品質 / プロファイリング / カタログ / グロッサリ / データプロダクト**を、自分のヘルスデータを題材に
「触って学ぶ」ための検証ストーリー集。

> 個人の勉強用リポなので業務上の必然性は低い。ドメイン知識のある実データで Dataplex の主要ガバナンス機能を
> 一通り体感するのが目的。

リネージが「辺」を描いたのに対し、以下は同じ Catalog を **プロファイル → 品質 → メタデータ → 用語 → プロダクト** と
リッチ化していく物語。

| # | ストーリー | 学びの核 | 状態 |
|---|---|---|---|
| **S1** | データプロファイリングスキャン | ルールを書かずに列統計を自動取得＝品質ルールの根拠 | ✅ 実装・検証済み |
| **S2** | データ品質スキャン（AutoDQ） | ドメインルールで継続監視。**SQLMesh audit との役割分担** | ✅ 実装・検証済み |
| **S3** | DQ の CI/Slack 連携 | 実行後ガバナンススキャン。best-effort no-op で `daily.yml` へ | 📄 設計のみ |
| **S4** | カタログエントリ＋アスペクト | 外部ソース一級化＋メタデータ台帳。既存 deferred『台帳』回収 | 📄 設計のみ |
| **S5** | ビジネスグロッサリ | 技術メタデータ↔ビジネス定義の橋渡し | 📄 設計のみ |
| **S6** | データプロダクト | 消費者に見せる単位。lineage/DQ/用語を 1 プロダクトに集約 | 📄 設計のみ |

インフラは初の IaC として [`../terraform/`](../terraform/) に集約（S1/S2 を管理。S3 以降で拡張）。

---

## 前提（環境）

- GCP project `pluse-board`（番号 `274885157237`）/ リージョン `asia-northeast1`（DataScan はリージョナル）
- SA `fitbit-dashboard@pluse-board.iam.gserviceaccount.com`
- データセット: `fitbit_raw`(JSON blob) / `fitbit_staging`(`stg_*` view) / `fitbit_mart`(`mart_*` view 10 本)
- `dataplex.googleapis.com` 有効化済み。予算アラート `1000JPY` 設定済み（DataScan は**無料枠なし**）

---

## 🔑 学び 0: DataScan は SQLMesh の VIEW でも動く

公式ドキュメントは「データプロファイル/品質スキャンは **BigQuery テーブル / Iceberg テーブルのみ**」と書き、
軽量プロファイルは明示的にビュー非対応とする。一方 **SQLMesh は全 prod モデルを仮想レイヤの VIEW として公開する**
（`fitbit_mart.mart_steps_daily` は VIEW → 物理は `sqlmesh__fitbit_mart.*__<fingerprint>`）。

→ 本リポで**実地検証した結果、プロファイル・品質スキャンとも `fitbit_mart.mart_steps_daily`（VIEW）で動作した**
（作成・実行・結果取得すべて成功）。物理テーブル名は fingerprint 付きで不安定なので、**VIEW を直接スキャン対象にできる**
のは本パイプラインをガバナンスするうえで重要。ドキュメントの記述は保守的で、実挙動はビューを許容している。

---

## 🔑 学び 1: 既存の検査層 vs Dataplex DQ（S2 の要）

本リポには既に「品質っぽい」仕組みが 3 つある。Dataplex DQ はそれらを**置換せず補完**する。

| 仕組み | 役割 | 実行タイミング | 失敗時 | 結果の残り方 |
|---|---|---|---|---|
| SQLMesh audits (`not_null`/`unique_values`/`assert_data_in_range`) | パイプライン内**ゲート** | モデル評価時 | **backfill を止める**（blocking） | ephemeral（ログのみ） |
| `ingest/check_health_data_freshness.py` | 取り込み鮮度ゲート | ingest 直後（CI） | CI を fail | ephemeral |
| **Dataplex DQ スキャン** | ガバナンス層の**継続監視** | スケジュール/オンデマンド（パイプライン外） | パイプラインは止めず**スコア記録・カタログ公開・アラート** | **履歴・可視化・BQ 公開** |

同じ `not_null(activity_date)` / `unique(activity_date)` を SQLMesh と Dataplex 双方に置き、
「ゲート（止める）」と「監視（記録し可視化する）」の違いを体感するのが S2 の狙い。SQLMesh の audit は
「壊れたデータを下流に流さない」ための門番、Dataplex DQ は「品質を経時的に測り公開する」ためのダッシュボード。

---

## S1: データプロファイリングスキャン ✅

ルールを書かずに列統計（null率 / distinct率 / min / max / 平均 / 分位 / 最頻値）を自動取得し、
S2 のルールしきい値の「根拠＝現状把握」を得る。

- **実装**: `terraform/datascans.tf` の `google_dataplex_datascan.mart_steps_profile`（`data_profile_spec {}`）
- **対象**: `fitbit_mart.mart_steps_daily`（VIEW）
- **トリガー**: `on_demand`（学習用途。無料枠なしなので課金を垂れ流さない）

### 検証結果（`mart_steps_daily`）

| 列 | 型 | rowCount | nullRatio | distinctRatio | min | max | avg |
|---|---|---|---|---|---|---|---|
| `activity_date` | DATE | 98 | 0 | 1.0（完全一意） | — | — | — |
| `steps` | INT64 | 98 | 0 | — | **1825** | **19253** | **6117** |

→ この実測から S2 のしきい値を決めた（範囲上限 100000 は max=19253 に対し十分安全側／
故意 FAIL は max より小さい `steps <= 10000` で作れる、など）。

> **Terraform カバレッジのギャップ（学び）**: provider google v6.50 の `data_profile_spec` には
> catalog 公開フィールドが無い（`data_quality_spec.catalog_publishing_enabled` のみ対応）。
> プロファイル結果を BigQuery「データプロファイル」タブに公開したい場合は gcloud の
> `--enable-catalog-publishing` を使う。TF 管理リソースに gcloud で設定を足すと drift するため、
> 本リポではプロファイルは「スキャン結果ページで閲覧」に留め、公開は将来の課題とする。

---

## S2: データ品質スキャン（AutoDQ）✅

ドメイン知識ベースのルールを宣言し、PASS/FAIL・次元別スコアを継続監視する。

- **実装**: `terraform/datascans.tf` の `google_dataplex_datascan.mart_steps_quality`
  （`data_quality_spec { catalog_publishing_enabled = true; rules {...} }`）
- **対象**: `fitbit_mart.mart_steps_daily`（VIEW）

### ルール設計

| ルール | dimension | 期待タイプ | 意図 |
|---|---|---|---|
| `activity_date` NOT NULL | COMPLETENESS | `non_null_expectation` | SQLMesh not_null audit と同じ意図を監視層でも |
| `activity_date` UNIQUE | UNIQUENESS | `uniqueness_expectation` | SQLMesh unique_values audit と対比 |
| `steps` ∈ [0, 100000] | VALIDITY | `range_expectation` | ドメイン上限（プロファイル実測 max=19253 → 安全側） |
| `MAX(activity_date) >= today-2` | FRESHNESS | `table_condition_expectation` | 日次取り込みの鮮度を監視層でも |
| **（故意 FAIL）** `steps <= 10000` | VALIDITY | `row_condition_expectation` | FAIL の見え方・行内訳を体感（`include_demo_failing_rule` で切替） |

### 検証結果

全体 **score: 80.0**（5 ルール中 4 PASS）。次元別: COMPLETENESS ✅ / UNIQUENESS ✅ / FRESHNESS ✅ / VALIDITY は混在。

| 判定 | dimension | ルール | passRatio | 内訳 |
|---|---|---|---|---|
| ✅ PASS | COMPLETENESS | `activity_date` nonNull | 1.0 | 98/98 |
| ✅ PASS | UNIQUENESS | `activity_date` unique | 1.0 | 98/98 |
| ✅ PASS | VALIDITY | `steps` range 0–100000 | 1.0 | 98/98 |
| ✅ PASS | FRESHNESS | 最新日 ≤ 2 日前 | — | table 条件成立 |
| ❌ **FAIL** | VALIDITY | `steps <= 10000`（故意） | **0.857** | 84/98（14 日が 1 万歩超。max=19253 と整合） |

→ **意図した通り**、正常な 4 ルールは全 PASS、現実に反する 1 ルールだけが FAIL し、
`row_condition_expectation` は行単位の passRatio（0.857）で「どれだけ外れたか」を返す。
`catalog_publishing_enabled=true` なので、このスコアは BigQuery コンソール `mart_steps_daily` の
「データ品質」タブ / Dataplex Catalog にも公開される。

### 故意 FAIL を外して正常系に戻す

```bash
cd terraform
echo 'include_demo_failing_rule = false' >> terraform.tfvars
terraform apply
gcloud dataplex datascans run mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board
# → score 100.0（全 PASS）になる
```

---

## S1/S2 runbook（再現手順）

```bash
cd terraform
terraform init
terraform plan          # 差分確認（DataScan 2 本 + API 有効化。IAM 変更なし）
terraform apply

# 手動実行（on_demand）
gcloud dataplex datascans run mart-steps-daily-profile --location=asia-northeast1 --project=pluse-board
gcloud dataplex datascans run mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board

# 結果確認（CLI）
gcloud dataplex datascans jobs list --datascan=mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board
gcloud dataplex datascans jobs describe <JOB_ID> --datascan=mart-steps-daily-quality \
  --location=asia-northeast1 --project=pluse-board --view=FULL

# 結果確認（コンソール）: BigQuery → fitbit_mart.mart_steps_daily →「データプロファイル」/「データ品質」タブ、
#                          または Dataplex → データスキャン
```

拡張候補: `mart_acwr`（ACWR の null 率＝28日窓が埋まるまで NULL、非 null 行は 0.8–1.3 が健全域）、
`stg_exercise`（`exercise_type` の enum を `set_expectation`、`end_time > start_time` を `row_condition`）、
`mart_strength_streak`（`current_streak_weeks <= best_streak_weeks` を `row_condition`）。

---

## S3: DQ の CI/Slack 連携 📄（設計のみ）

**狙い**: パイプライン実行後にガバナンススキャンを回すオーケストレーション。lineage と同じ **best-effort no-op** で。

- `.github/workflows/daily.yml` の SQLMesh run 後に、`gcloud dataplex datascans run mart-steps-daily-quality ...` を
  1 ステップ追加（`continue-on-error: true` 相当の best-effort。失敗してもパイプラインは止めない）。
- CI SA `fitbit-dashboard@...` に **`roles/dataplex.dataScanEditor` が必要** → `terraform/variables.tf` の
  `grant_ci_datascan_role=true` で追記付与（AGENTS.md により IAM 変更は要承認）。
- **DQ FAIL の通知**: 既存の Slack/beads 連携（[`slack-integration-design.md`](slack-integration-design.md) /
  `daily-build-triage.yml`）に、スキャンジョブの `dataQualityResult.passed=false` を検知して起票/通知するステップを足す。
  Dataplex の `notification_report`（`google_dataplex_datascan` の `post_scan_actions.notification_report`）で
  email 通知も可能だが、本リポは Slack 起票が既存基盤なのでそちらに寄せる。
- 認証は lineage と同じ WIF access_token を流用できる。

---

## S4: カタログエントリ＋アスペクト 📄（設計のみ）

**狙い**: 既存の未着手『台帳』回収（[`openlineage-dataplex-design.md`](openlineage-dataplex-design.md) の「次のステップ」）。
lineage の**参照ノード**（`custom:googlehealth:activity/*`）と Catalog **エントリ**の違いを実践する。

- **(a) 外部ソースの一級エントリ化**: Entry Group を作り、FQN が lineage ノードと一致する Entry を登録
  （[ingest-custom-sources](https://docs.cloud.google.com/dataplex/docs/ingest-custom-sources)）。
  → lineage グラフの外部ノードをクリックすると「エントリなし」ではなく実体（説明・スキーマ）が見えるようになる。
- **(b) Aspect Type**: `data-owner` / `update-frequency` / `sensitivity=health(PII)` などの構造化メタデータ型を定義し、
  `mart_*` エントリに付与。
- **(c) 検索**: Dataplex Catalog search で属性検索（`sensitivity=health` 等）がヒットすることを確認。
- Terraform 対応: `google_dataplex_entry_group` / `google_dataplex_aspect_type` / `google_dataplex_entry` は一部対応。
  TF で書けない部分は gcloud/コンソール併用（対応状況の確認自体が学び）。

---

## S5: ビジネスグロッサリ 📄（設計のみ）

**狙い**: 技術メタデータ（スキーマ）とビジネス定義の橋渡し。個人プロジェクトでもドメイン用語は多い。

- Business Glossary に用語を定義しカラムに紐付け:
  - **ACWR**（Acute:Chronic Workload Ratio、健全域 0.8–1.3）→ `mart_acwr.acwr`
  - **トレーニング負荷**（AZM 日次合計）→ `mart_load_daily.load`
  - **アクティブゾーン分**（AZM）→ `stg_active_zone_minutes.value`
  - **筋トレ達成**（週 3 回以上で `meets_target=true`）→ `mart_strength_weekly.meets_target`
- カラムのエントリから用語定義に辿れることを確認。
- Terraform 対応は限定的 → gcloud/コンソールが主。

---

## S6: データプロダクト 📄（設計のみ）

**狙い**: 「消費者に見せる単位」の設計。lineage / DQ / catalog / glossary を 1 プロダクトビューに集約する。

- キュレーションしたマート群を 1 プロダクト化:
  - 『トレーニング負荷モニタリング』= `mart_load_daily` + `mart_acwr` + `mart_exercise_weekly`
  - 『筋トレ継続』= `mart_strength_daily` + `mart_strength_weekly` + `mart_strength_streak`
- 説明・オーナー・品質スコア（S2）・用語（S5）・利用方法を束ねて公開。
- ⚠ **提供状況の確認自体が検証の一部**: Data Product は比較的新しい機能。gcloud/API/コンソール対応・
  リージョン対応・Terraform 対応を先に確認する。使えなければ「なぜ／代替（キュレーテッド Entry Group で近似）」を
  学びとして記録する。

---

## コスト / 後片付け

- DataScan は DCU 課金・**無料枠なし**。`on_demand` トリガー＋対象 1 テーブルなら実測は極小想定。
- 課金 SKU は Cloud Billing で `goog-dataplex-workload-type` 系ラベルを数日観察（lineage の runbook と同じ手法）。
- 学習が済んだら `cd terraform && terraform destroy` でスキャンを削除（`dataplex` API は
  `disable_on_destroy=false` のため無効化しない）。
