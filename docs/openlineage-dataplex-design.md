# OpenLineage / Dataplex データリネージ 設計・手順

## Context

pluse-board のデータパイプライン
`Google Health API → ingest(Python) → BigQuery raw → SQLMesh(staging/mart) → Evidence → GitHub Pages`
に対して、**データリネージ（どのデータがどこから来てどこへ行くか）** を可視化する。学習も兼ねて OpenLineage を採用し、GCP ネイティブの **Dataplex（2026/4 以降「Knowledge Catalog」。API 名は不変）** に集約する。

到達したい学び:
1. **OpenLineage 仕様そのもの**（Run / Job / Dataset / Facet）を reference 実装 **Marquez** の UI で体感する。
2. **GCP ガバナンス**として、OpenLineage イベントと BigQuery 自動リネージが Dataplex 上で 1 枚のグラフに統合される様子を見る。

> **Status**: Phase 0（BQ 自動リネージ有効化）・Phase 1（Python 取り込みの OpenLineage 自作）は**実装済み・検証済み**。Phase 3（CI 組込み）着手中。Phase 2（SQLMesh の lineage）は未着手。台帳（カスタムエントリ登録）は別 beads タスク。

## 全体像（3 層のリネージ）

同じパイプラインを 3 通りの方法でリネージ化でき、それぞれ守備範囲が違う:

| 層 | 取得方法 | 実装 | 状態 |
|---|---|---|---|
| BigQuery の SQL 変換（staging→mart） | Data Lineage API 有効化で**テーブル/カラム自動取得** | コード不要 | ✅ Phase 0 |
| Python 取り込み（Health API → `fitbit_raw`） | BQ が見られない API 起点の辺を **OpenLineage 自作**で埋める | `ingest/lineage.py` | ✅ Phase 1 |
| SQLMesh の論理 DAG / 実行統計 | `sqlmesh-openlineage` で START/COMPLETE/FAIL + カラム lineage | 未 | ⬜ Phase 2 |

```mermaid
flowchart LR
    API[Health API]
    Raw[(fitbit_raw)]
    Stg[(fitbit_staging)]
    Mart[(fitbit_mart)]

    API -->|OpenLineage 自作<br/>ingest/lineage.py| Raw
    Raw -->|BQ 自動リネージ| Stg
    Stg -->|BQ 自動リネージ| Mart
```

Phase 1 の Dataset 命名を BQ 自動リネージと一致させることで、`API → raw → staging → mart` が**1 本のグラフに地続き**になるのが肝（後述）。

## コスト

- **Dataplex Data Lineage** = premium processing 課金 **$0.089 / DCU-hour・無料枠なし**、metadata ストレージ **$2/GiB・月**（1 MiB 無料）。
- 本プロジェクト規模（16 モデル + 日次数件の ingest イベント）では DCU 消費は極小 → 実質 **月 $0〜数ドル、おそらく $1 未満**。
- **BigQuery のクエリ課金は増えない**（lineage 収集はクエリ課金に載らない）。**Marquez ローカルは無料**（Docker）。
- 無料枠が無いので厳密には $0 ではない → **予算アラート必須**（Phase 0 で先に設定）。
- 「テーブルを細かく何度も更新すると lineage イベントが増える」点に注意。現状の日次 incremental 設計は問題なし。
- 実測は Cloud Billing でラベル `goog-dataplex-workload-type=LINEAGE` の SKU を数日観察して確認する。

---

## Phase 0: BQ ネイティブ lineage の有効化（GCP 設定・コード不要）

「自動で何が取れるか」を体感し、Python で埋めるべき欠落（API→raw の辺）を明確にするフェーズ。

### 1. Data Lineage API 有効化

```bash
gcloud services enable datalineage.googleapis.com --project pluse-board
```

> この 1 つの API が「BigQuery 自動リネージ」と「OpenLineage 受け皿（`processOpenLineageRunEvent`）」の両方を兼ねる。

### 2. IAM

```bash
# 観察用（owner でも明示が確実）
gcloud projects add-iam-policy-binding pluse-board \
  --member="user:marufeuille@gmail.com" --role="roles/datalineage.viewer"
# OpenLineage を emit する側（自分＝ローカル producer）
gcloud projects add-iam-policy-binding pluse-board \
  --member="user:marufeuille@gmail.com" --role="roles/datalineage.editor"
# SQLMesh を実行する CI の SA（自動/カスタム lineage 記録用）
gcloud projects add-iam-policy-binding pluse-board \
  --member="serviceAccount:fitbit-dashboard@pluse-board.iam.gserviceaccount.com" \
  --role="roles/datalineage.editor"
```

### 3. 予算アラート（無料枠が無いので先に張る）

```bash
gcloud services enable billingbudgets.googleapis.com --project pluse-board
# 請求アカウント通貨に合わせる（日本は JPY。USD 指定は INVALID_ARGUMENT になる）
gcloud billing budgets create \
  --billing-account=<BILLING_ACCOUNT_ID> \
  --display-name="pluse-board budget guard" \
  --filter-projects=projects/274885157237 \
  --budget-amount=1000JPY \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

> CLI が煩雑ならコンソール（Billing → 予算とアラート）でも可。

### 4. 観察

リネージは **API 有効化“以降”のジョブ**しか記録されない。新しい BQ ジョブを 1 本流して確認する:

```bash
bq query --use_legacy_sql=false --location=asia-northeast1 \
'CREATE OR REPLACE TABLE `pluse-board.fitbit_mart._lineage_demo` AS
 SELECT * FROM `pluse-board.fitbit_mart.mart_load_daily` LIMIT 10'
```

数分後、BigQuery コンソール → `fitbit_mart._lineage_demo` →「リネージ」タブで、元テーブル→demo の辺（**カラム単位まで**）が自動で見える。確認後は掃除:

```bash
bq rm -f -t pluse-board:fitbit_mart._lineage_demo
```

**学び**: テーブル→テーブルは自動で出るが、`Health API → fitbit_raw` の**外部起点の辺は絶対に出ない**。ここを Phase 1 で埋める。

---

## Phase 1: Python 取り込みの OpenLineage 自作

### ローカル Marquez（OpenLineage の“標準の見え方”）

```bash
cd ~/dev && git clone https://github.com/MarquezProject/marquez.git
cd marquez && ./docker/up.sh --api-port 9000 --web-port 3000
```

- API :9000 / Web UI :3000（http://localhost:3000）。
- **API を 9000 にする理由**: macOS は 5000 番を AirPlay Receiver が握るため、既定 :5000 だと競合/403 が起きやすい。
- 疎通確認: `curl -s http://localhost:9000/api/v1/namespaces`

### OpenLineage イベントの構造（学習メモ）

RunEvent はたった 5 要素の組み合わせ:

| フィールド | 意味 | ポイント |
|---|---|---|
| `eventType` | `START`/`RUNNING`/`COMPLETE`/`FAIL`/`ABORT` | 1 回の実行を複数イベントで表す |
| `run.runId` | 実行 1 回を指す UUID | START と COMPLETE を**同じ runId で紐付ける** |
| `job` | 論理的な処理ステップ（namespace + name） | 繰り返し動く処理の identity |
| `inputs`/`outputs` | 消費/生成した **Dataset** | ここが辺（lineage）になる |
| `producer`/`schemaURL` | 誰が/どの仕様で出したか | メタ情報 |

### Dataset 命名規約（最重要）

| ソース種別 | namespace | name | 効果 |
|---|---|---|---|
| BigQuery テーブル | `bigquery` | `project.dataset.table` | **BQ 自動リネージと同じノードに解決**され地続きに |
| 外部ソース（API 等） | `custom` | 任意の参照文字列 | FQN `custom:...` にマップ |

> **Dataplex 固有のクセ**: 外部ソースは `namespace: "custom"` にしないと `INVALID_ARGUMENT: Unrecognized input` で弾かれる（Marquez は緩いので何でも受ける）。本プロジェクトでは Health API を `custom` / `googlehealth:activity/<data_type>` と命名。

### 実装: `ingest/lineage.py`

OpenLineage 送信ヘルパ。**transport は環境変数だけで決まる**（`OpenLineageClient()` が env を読む）ので、モジュールはバックエンド非依存。

- `ingest/pull_health_api.py` の data_type ループを `with track_ingest(...)` で包み、START→COMPLETE（例外時 FAIL）を emit。
- **安全設計**: lineage は「副次情報」。`OPENLINEAGE_URL` 未設定なら完全 no-op、openlineage 未導入や送信失敗でも `::warning::` を出すだけで **ingest 本体は絶対に止めない**。→ CI（`uv sync --only-group ingest`、openlineage 無し）でも壊れない。

環境変数による transport 切替:

```bash
# ローカル Marquez
OPENLINEAGE_URL=http://localhost:9000

# Dataplex（Knowledge Catalog）
OPENLINEAGE_URL=https://datalineage.googleapis.com
OPENLINEAGE_ENDPOINT=v1/projects/pluse-board/locations/asia-northeast1:processOpenLineageRunEvent
OPENLINEAGE_API_KEY=$(gcloud auth print-access-token)   # ADC の Bearer トークン

# 無効化（既定）
# OPENLINEAGE_URL を設定しない、または OPENLINEAGE_DISABLED=true
```

### 検証

```bash
# 依存追加
uv add --group lineage openlineage-python

# ① スモーク（実データ・BQ に触れず emit だけ）→ Marquez
uv run --group lineage python ingest/lineage.py
#   → http://localhost:3000 の pluse-board namespace に ingest.exercise ジョブ

# ② 同じコードで Dataplex（env だけ差し替え）
OPENLINEAGE_URL=https://datalineage.googleapis.com \
OPENLINEAGE_ENDPOINT=v1/projects/pluse-board/locations/asia-northeast1:processOpenLineageRunEvent \
OPENLINEAGE_API_KEY=$(gcloud auth print-access-token) \
uv run --group lineage python ingest/lineage.py
#   → 数分後 BQ コンソール fitbit_raw.exercise のリネージに API 起点の辺

# ③ 実データでエンドツーエンド（Health API OAuth env が必要）
set -a; source .env; set +a
OPENLINEAGE_URL=http://localhost:9000 \
uv run --group ingest --group lineage python ingest/pull_health_api.py --lookback-days 1
```

---

## 学びメモ: 「リネージ」と「カタログ」は別物

Knowledge Catalog には 2 つのサブシステムがある:

| サブシステム | 役割 | 誰が作るか |
|---|---|---|
| **Data Lineage**（辺・グラフ） | どこから来てどこへ行くか | OpenLineage イベント |
| **Catalog エントリ**（メタデータ台帳） | 各アセットの説明・スキーマ・検索対象 | BigQuery は**自動**、外部ソースは**手動** |

- BQ テーブルのノードがクリックして中身を見られるのは、Catalog エントリが自動生成されるから。
- 外部ノード `custom:googlehealth:...` は lineage が辺を描くための参照ノードで、Catalog エントリ本体は無い → 詳細ペインが「エントリが存在しない」と出る（**想定どおり**、lineage 目的では問題なし）。
- 外部ソースも検索可能な一級エントリにしたい場合は、Entry Group + FQN 一致の Entry を手動作成する（[ingest-custom-sources](https://docs.cloud.google.com/dataplex/docs/ingest-custom-sources)）。→ 別 beads タスクで対応。

---

## 次のステップ

- **Phase 3（CI 組込み）**: `.github/workflows/daily.yml` の ingest ステップに lineage 用 env を注入し、WIF の ADC からトークンを取得して Dataplex へ投入。`uv sync` に `--group lineage` を追加。既定 no-op のため段階的に有効化できる。
- **Phase 2（SQLMesh の lineage）**: `sqlmesh-openlineage` でカラム lineage + 実行統計。`config.yaml` を壊さない案（薄いランナー）を Marquez で先に spike してから採否を決める。
- **台帳（カスタムエントリ登録）**: Health API 外部ソースを Knowledge Catalog の一級エントリにする（beads タスク管理）。
- **Dataplex ガバナンス機能の学習**: lineage（辺）の先に、データ品質 / プロファイリング / カタログ / グロッサリ / データプロダクトを実データで触る検証ストーリー集 → [`dataplex-governance-stories.md`](dataplex-governance-stories.md)。S1/S2（プロファイル/品質スキャン）は初 IaC の [`../terraform/`](../terraform/) で実装・検証済み。
