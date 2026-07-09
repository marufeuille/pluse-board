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
| **S3** | DQ の CI/Slack 連携 | 実行後ガバナンススキャン。best-effort no-op で `daily.yml` へ | ✅ 実装・検証済み |
| **S4** | カタログエントリ＋アスペクト | 外部ソース一級化＋メタデータ台帳。既存 deferred『台帳』回収 | ✅ 実装・検証済み |
| **S5** | ビジネスグロッサリ | 技術メタデータ↔ビジネス定義の橋渡し | 📄 設計のみ |
| **S6** | データプロダクト | 消費者に見せる単位。lineage/DQ/用語を 1 プロダクトに集約 | 📄 設計のみ |

インフラは初の IaC として [`../terraform/`](../terraform/) に集約（S1／S2／S4 を管理。S5 以降で拡張）。

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

コミット構成に含まれるのはこの 4 ルール（全て正常系）。トリガーは当初 S2 でデイリースケジュール
（`0 1 * * *` UTC = 10:00 JST）にしていたが、**S3 で `on_demand` に戻し Daily Build から起動する**ようにした。
プロファイルは当初から `on_demand`。

### 検証結果

正常 4 ルールは全 PASS（**score 100.0**）。次元別も COMPLETENESS ✅ / UNIQUENESS ✅ / VALIDITY ✅ / FRESHNESS ✅。

| 判定 | dimension | ルール | passRatio | 内訳 |
|---|---|---|---|---|
| ✅ PASS | COMPLETENESS | `activity_date` nonNull | 1.0 | 98/98 |
| ✅ PASS | UNIQUENESS | `activity_date` unique | 1.0 | 98/98 |
| ✅ PASS | VALIDITY | `steps` range 0–100000 | 1.0 | 98/98 |
| ✅ PASS | FRESHNESS | 最新日 ≤ 2 日前 | — | table 条件成立 |

`catalog_publishing_enabled=true` なので、このスコアは BigQuery コンソール `mart_steps_daily` の
「データ品質」タブ / Dataplex Catalog にも公開される。

> **学び（検証時の観察）**: 開発中に一時的に「現実に反するルール」`steps <= 10000` を足して FAIL の見え方も確認した。
> 結果は passRatio **0.857**（98 日中 84 日のみ成立。max=19253 と整合）で、`row_condition_expectation` は
> 行単位で「どれだけ外れたか」を返すと分かった。この故意 FAIL ルールは**本番コードには残していない**
> （検証専用。学習の記録としてここに残す）。

---

## S1/S2 runbook（再現手順）

```bash
cd terraform
terraform init
terraform plan          # 差分確認（DataScan 2 本 + API 有効化。IAM 変更なし）
terraform apply

# 品質スキャンは Daily Build（S3）から起動される。手元から即時に走らせたいときは:
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

## S3: DQ の CI/Slack 連携 ✅

**狙い**: パイプライン実行後にガバナンススキャンを回すオーケストレーション。lineage と同じ **best-effort no-op** で。

S2 の時点では品質スキャンは Dataplex 側のデイリースケジュール（10:00 JST）で孤立して回っており、
**FAIL しても誰も気付けなかった**。S3 でスキャンを Daily Build に引き込み、「新鮮なデータの直後に同期的に
合否を判定し、FAIL を既存の beads/Slack 基盤へ流す」形にした。

### 実装

| 何を | どこで |
|---|---|
| 品質スキャンのトリガーを `schedule` → `on_demand` へ | `terraform/datascans.tf` |
| CI SA に DataScan ロールを追記付与（`grant_ci_datascan_role` 既定 `true`） | `terraform/iam.tf` |
| スキャン起動 → 完了待ち → 合否抽出 | `scripts/dataplex_dq_scan.sh`（新規） |
| SQLMesh run 直後にスキャンを実行し、FAIL なら通知ジョブへ | `.github/workflows/daily.yml` |

- **認証**: lineage と同じ WIF の短命 access_token（`steps.auth.outputs.access_token`）を Bearer に流用。
  gcloud CLI に依存せず Dataplex REST API（`dataScans/{id}:run` → `dataScanJobs.get?view=FULL`）を curl で叩く。
- **通知**: `daily.yml` の `notify_dq` ジョブが `dataQualityResult.passed=false` のときだけ走り、
  `daily-build-triage.yml` と同じ dedupe パターン（タイトル完全一致 → `bd comment` / なければ `bd q`）で beads 起票、
  続けて Slack に通知する。Dataplex ネイティブの `post_scan_actions.notification_report`（email）は
  「見ないので不採用」とし、既存の Slack/beads 基盤に寄せた。
- **実行契機**: Daily Build の全実行（`push` 含む）。1 スキャン ≈ $0.0015 なのでコスト増は無視できる。
- **直列化**: `notify_dq` の `concurrency.group` を `slack-beads-create.yml` と同じ `beads-slack` にして、
  DoltHub への push レースを防ぐ。

### 🔑 学び: `dataScanEditor` だけでは合否が読めない

CI SA に必要なロールは 1 つではなく 2 つだった。

| ロール | 与えるもの |
|---|---|
| `roles/dataplex.dataScanEditor` | スキャンの**起動**（`dataplex.datascans.run`）とジョブのメタデータ取得 |
| `roles/dataplex.dataScanDataViewer` | ジョブ結果の**中身**（`dataQualityResult` = 合否・スコア・ルール別内訳）の閲覧 |

Editor だけだとジョブ自体は GET できるのに `dataQualityResult` が返らない。ここで「レスポンスに `passed` が
無い＝PASS」と読むと **FAIL を握り潰す**ので、スクリプトは `passed` が空なら `status=error` に倒している。

### 🔑 学び: FAIL 時は `passed` フィールドが JSON から**消える**

実装中に実データで踏んだ罠。Dataplex の REST レスポンスは proto3 の既定値省略に従うため、
**`dataQualityResult.passed` は `false` のときフィールドごと存在しない**（`rules[].passed` も同じ）。

```jsonc
// PASS のジョブ
{ "dataQualityResult": { "passed": true, "score": 100, ... } }
// FAIL のジョブ … passed が無い！
{ "dataQualityResult": {            "score": 80,  ... } }
```

素直に書くと 2 通りの読み間違いが同時に起きる。

| 素直な実装 | 実際の挙動 |
|---|---|
| `passed` が無い → 「結果を読めていない」と判定 | **FAIL がすべて `error` に化けて通知されない** |
| `select(.passed == false)` で失敗ルールを抽出 | `null == false` は偽なので **1 件も拾えない** |

対処: 結果を読めたかどうかは `has("dataQualityResult")` で判定し、`passed` は `// false` に倒す。
失敗ルールの抽出は `select(.passed != true)`。S2 の故意 FAIL ジョブ（score 80）の実 JSON で両方を検証した。

### 🔑 学び: 通知アクションは既定でサイレント失敗する

FAIL 経路を実地検証したら、`notify_dq` の全ステップが success なのに **Slack に何も届かなかった**。
原因は `slackapi/slack-github-action` の既定 **`errors: false`** — Slack API が `ok:false` を返しても
ステップを success にする。ログには API レスポンスすら出ない。

「通知が届かないのにパイプラインは緑」は、**監視の失敗としては最悪の形**（DQ FAIL を見逃す）。
`errors: true` を明示して失敗を検出しつつ、`continue-on-error: true` を **step に**付けて握る。
job や workflow を failure にすると `daily-build-triage` が誤発火してしまうため。
失敗時は後続ステップが `::error::` アノテーションと Step Summary を残す。beads 起票は Slack より
前に済んでいるので、Slack が落ちても通知そのものは失われない。

同じ既定値の穴が `slack-beads-create.yml` にもあったので併せて塞いだ。

**この既定値が実際に隠していた不具合**: 当初は「Slack App を通知先チャンネルに追加し忘れたので
`not_in_channel` だろう」と推測していた。App を追加しても届かず、`errors: true` にして初めて
真因が **`missing_scope`**（bot token に `chat:write` が無い）だと分かった。
サイレント失敗は原因究明そのものを止める — エラーを握り潰すと、間違った仮説で時間を溶かす。

### 🔑 設計判断: 「測れなかった」と「品質が悪い」を分ける

スクリプトの出力は 3 値。

| status | 意味 | 挙動 |
|---|---|---|
| `pass` | 全ルール成立 | 何もしない |
| `fail` | `dataQualityResult.passed=false` | `notify_dq` が beads 起票 + Slack 通知 |
| `error` | 起動失敗・タイムアウト・結果が読めない | `::warning::` のみ。**通知しない** |

`error` を通知に乗せないのは、品質の話ではなくインフラの話だから。ただしこれは
「スキャンがずっと壊れていても静かに見逃す」というトレードオフでもある。将来は `error` の連続回数を
数えて別経路（Daily Build triage 側）に上げるのが筋。

いずれの status でも **exit 0**。lineage（`ingest/lineage.py`）と同じで、ガバナンス層の都合で
パイプラインと Pages デプロイを止めない（`deploy` は `needs: build` のまま）。

### 検証結果

| ルート | 手段 | 結果 |
|---|---|---|
| PASS | 正常 4 ルールでスクリプトをローカル実行（実スキャン起動） | `status=pass` / `score=100` / exit 0 |
| error | 存在しない `DATASCAN_ID` を渡す | 404 → `::warning::` / `status=error` / **exit 0** |
| FAIL | 故意 FAIL ルール（`steps <= 10000`）を一時 apply し Daily Build を手動実行 | `status=fail` / score 80 / 失敗ルール 1 件（`VALIDITY steps` passRatio 0.859、85/99） |

FAIL 経路では `notify_dq` が発火し、beads issue `pluse-board-dyt` が score・失敗ルール・ジョブ名・Run URL 付きで
自動起票され、DoltHub まで同期された。`build` / `deploy` はどちらも success のままで、
**DQ FAIL が Pages デプロイを止めないこと**も確認できた。Slack だけは上記のサイレント失敗を踏んでいた。
検証後、故意ルールは revert して apply し直している。

> **Slack の前提**: 次の 3 つが揃って初めて通知が届く。
> 1. `SLACK_BOT_TOKEN`（secret）— **Bot Token Scopes に `chat:write` が必要**。付け忘れると `missing_scope`
> 2. `SLACK_ALERT_CHANNEL_ID`（variable）
> 3. Slack App がその**チャンネルに追加されている**こと。でないと `not_in_channel`
>
> 1・2 が未設定のうちは Slack ステップが `if: env.… != ''` でスキップされる（beads 起票だけで通知は成立する）。
> job レベルの `if` からは `secrets` コンテキストを参照できないため、job レベル `env` に落として step の `if` で判定している。

---

## S4: カタログエントリ＋アスペクト ✅

**狙い**: 既存の未着手『台帳』回収（[`openlineage-dataplex-design.md`](openlineage-dataplex-design.md) の「次のステップ」）。
lineage の**参照ノード**と Catalog **エントリ**の違いを、実物を作って体感する。

lineage は辺を描くために FQN を参照するだけで、エントリの実体を作らない。だから
`custom:googlehealth:activity/*` をクリックすると「エントリが存在しない」と出ていた。
**同じ FQN を持つ Entry を後から登録すると、その参照が実体に解決される**——これが S4 の核心。

### 実装

| 何を | どこで |
|---|---|
| Entry Group `googlehealth-sources`（`asia-northeast1`） | `terraform/catalog.tf` |
| Entry × 3（FQN が lineage ノードと厳密一致） | 同上（`for_each` で `ENABLED_DATA_TYPES` と対応） |
| Aspect Type `governance-metadata`（`data_owner` / `update_frequency` / `sensitivity`） | 同上 |
| 既存 BigQuery エントリ `mart_steps_daily` への付与 | `gcloud dataplex entries update-aspects`（`terraform/README.md` の runbook） |

エントリ ID は `activity-{exercise,steps,active_zone_minutes}`、FQN は `custom:googlehealth:activity/<data_type>`。
`ingest/lineage.py` が emit する `namespace="custom"` + `name="googlehealth:activity/<data_type>"` と一致させている。

### 🔑 学び: Terraform 対応は「一部」ではなく揃っていた

設計時は「`entry_group` / `aspect_type` / `entry` は一部対応」と書いていたが、**provider google v6.50 では
4 リソース（`entry_group` / `entry_type` / `aspect_type` / `entry`）すべて存在する**（`terraform providers schema -json` で確認）。
S4 の (a)(b) は Terraform だけで書けた。

TF で書けないのは **`@bigquery` エントリへのアスペクト付与**だけ。BigQuery のエントリは Dataplex が
`@bigquery` エントリグループに**自動生成する TF 管理外リソース**なので、`google_dataplex_entry` では管理できない。

> **drift の整理**: S1 では「TF 管理下の DataScan に gcloud で `--enable-catalog-publishing` を足すと drift する」
> ので公開を見送った。今回は事情が逆で、**TF 管理下の 3 エントリには TF の `aspects` ブロックで付け、
> TF 管理外の `@bigquery` エントリにだけ gcloud を使う**。管理境界と操作手段が一致しているので drift しない。

### 🔑 学び: Entry 系はプロジェクト「番号」、search 述語はプロジェクト「ID」

同じアスペクトを指すのに、API と検索で表記が違う。

| 文脈 | 表記 | 例 |
|---|---|---|
| `google_dataplex_entry` の `project` / `entry_type` | **番号** | `projects/655216118709/locations/global/entryTypes/generic` |
| アスペクトキー（TF の `aspect_key` / gcloud の `--aspects` JSON) | **番号** | `274885157237.asia-northeast1.governance-metadata` |
| Catalog search の `aspect=` 述語 | **ID** | `aspect=pluse-board.asia-northeast1.governance-metadata` |

`entry_type` に `projects/dataplex-types/...`（gcloud が返す ID 表記）を書くと **`terraform validate` が弾く**
（`Expected format: 'projects/<project-number>/<anything>'`）。`dataplex-types` の番号は `655216118709`。
逆に search で番号表記を渡すと**エラーにならず 0 件が返る**——サイレントに空振りするので質が悪い。

### 🔑 学び: `generic` Entry Type は `generic` Aspect を必須で要求する

カスタムエントリに使えるシステム Entry Type は再利用可能な `generic` のみ（`bigquery-table` 等は restricted）。
ところが `generic` は `requiredAspects` に**同名の `generic` Aspect Type** を持つ。知らずに apply すると:

```
Error 400: Missing required Aspect(s): projects/655216118709/locations/global/aspectTypes/generic
```

`generic` アスペクト自体は `type` / `system` の 2 フィールド（どちらも optional）だけ。**中身は空でもよいが、
アスペクトとしては付いていなければならない**。`catalog.tf` では `type="activity-stream"` / `system="Google Health API"` を入れた。

### 検証結果

エントリと FQN（`gcloud dataplex entries describe`）:

| 確認項目 | 結果 |
|---|---|
| `fullyQualifiedName` | `custom:googlehealth:activity/exercise` ✅ lineage ノードと一致 |
| アスペクト | `274885157237.asia-northeast1.governance-metadata`（HEALTH / DAILY / owner）＋ `655216118709.global.generic` |
| `entryType` | `projects/655216118709/locations/global/entryTypes/generic` |
| apply 後の `terraform plan` | **差分なし**（番号表記でも恒常 diff は出ない） |

lineage 側との突き合わせ（Data Lineage API `:searchLinks`）:

```
custom:googlehealth:activity/exercise  ->  bigquery:pluse-board.fitbit_raw.exercise
```

lineage が記録している FQN と Catalog エントリの FQN が**両側の API で文字列一致**していることを確認した
（コンソールでの詳細ペインの見え方は目視確認に委ねる）。

`@bigquery` の `mart_steps_daily` への付与:

- エントリ ID は `DATASET.TABLE` ではなく**フルリソースパス**
  （`.../entryGroups/@bigquery/entries/bigquery.googleapis.com/projects/.../datasets/fitbit_mart/tables/mart_steps_daily`）。
  公式ドキュメントの `DATASET.TABLE` 表記では `NOT_FOUND` になる。
- `update-aspects` は**既存アスペクトを保ったままマージ**する。付与後も
  `bigquery-view` / `data-quality-scorecard`（S2 の catalog publishing の成果）/ `schema` / `usage` は残った。
- リージョナル（`asia-northeast1`）の Aspect Type を、同リージョンの `@bigquery` エントリに問題なく付与できた。

### 🔑 学び: Catalog search の値検索は `aspect:` 接頭辞が要る

`sensitivity=HEALTH` と素直に打っても **0 件**。正しくは `aspect:<aspect_type_id>.<field><op><value>`。
実測（対象は custom 3 本 + `mart_steps_daily` の計 4 本）:

| クエリ | ヒット |
|---|---|
| `googlehealth`（フリーテキスト） | 3（custom のみ） |
| `aspect:governance-metadata`（部分一致・存在検索） | **4** |
| `aspect=pluse-board.asia-northeast1.governance-metadata`（完全一致） | **4** |
| `aspect=274885157237.asia-northeast1.governance-metadata`（番号表記） | 0 |
| `aspect:governance-metadata.sensitivity=HEALTH` | **4** |
| `aspect:governance-metadata.sensitivity=PII` | 0 |
| `aspect:governance-metadata.update_frequency=DAILY` | **4** |
| `aspect:governance-metadata.data_owner:marufeuille`（`:` は部分一致） | **4** |
| `sensitivity=HEALTH`（接頭辞なし） | 0 |

`=PII` / `=WEEKLY` が 0 件で `=HEALTH` / `=DAILY` が 4 件なので、**存在検索ではなく値でフィルタされている**ことを確認できた。
文字列は `=`（完全一致）と `:`（部分一致）、数値は比較演算子も使える。
インデックス反映の遅延は体感されず、apply 直後から検索できた。

### コスト

Catalog の Entry / Aspect は **DCU を消費しない**（DataScan と違い compute が走らない）。課金対象はメタデータ
ストレージのみで、エントリ数本・数百バイトのアスペクトでは実質 **$0**。S1/S2 の DataScan とは性質が異なる。

---

## S5: ビジネスグロッサリ 📄（設計のみ）

**狙い**: 技術メタデータ（スキーマ）とビジネス定義の橋渡し。個人プロジェクトでもドメイン用語は多い。

- Business Glossary に用語を定義しカラムに紐付け:
  - **ACWR**（Acute:Chronic Workload Ratio、健全域 0.8–1.3）→ `mart_acwr.acwr`
  - **トレーニング負荷**（AZM 日次合計）→ `mart_load_daily.load`
  - **アクティブゾーン分**（AZM）→ `stg_active_zone_minutes.value`
  - **筋トレ達成**（週 3 回以上で `meets_target=true`）→ `mart_strength_weekly.meets_target`
- カラムのエントリから用語定義に辿れることを確認。
- Terraform 対応: provider v6.50 には `google_dataplex_glossary` / `_category` / `_term` が**ある**
  （S4 で Catalog 系リソースの実在を確認した際に併せて判明）。カラムへの紐付けは
  カラム単位アスペクトキー（`...@Schema.<column>`）を使うことになりそうで、そこは要検証。

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

- DataScan は premium processing = **$0.089/DCU-hour・無料枠なし**、秒課金・最低1分。消費 DCU は行数×列数に比例。
- 対象 `mart_steps_daily` は 98 行×2 列と極小 → 1 回 ≈ 0.017 DCU-hour ≈ **$0.0015/回**。
  品質を毎日 1 回 × 30 日 ≈ **月 $0.05 未満（数円〜十数円）**、実消費が数倍でも月 $1 未満。数ドルには届かない。
- 課金 SKU は Cloud Billing で `goog-dataplex-workload-type` 系ラベルを数日観察（lineage の runbook と同じ手法）。
- 学習が済んだら `cd terraform && terraform destroy` でスキャンを削除（`dataplex` API は
  `disable_on_destroy=false` のため無効化しない）。
