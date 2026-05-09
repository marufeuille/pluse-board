# pluse-board

Google Health API で取得した健康データ（運動・歩数・アクティブゾーン分）を、BigQuery → dbt → Evidence → GitHub Pages で可視化するダッシュボード。

## アーキテクチャ

```
Google Health API
      ↓ Python（日次取得）
BigQuery（raw layer）
      ↓ dbt-bigquery
BigQuery（mart layer）
      ↑
GitHub Actions（WIF で SA 借用）
      ↓ Evidence build
GitHub Pages
```

---

## 事前準備（手動作業）

以下の手順を順番に実施してください。コードの実装はこれらが完了していることを前提としています。

### 1. GCP プロジェクト準備

```bash
# プロジェクト作成（既存を使う場合はスキップ）
gcloud projects create YOUR_PROJECT_ID --name="pluse-board"
gcloud config set project YOUR_PROJECT_ID

# 必要な API を有効化
gcloud services enable \
  health.googleapis.com \
  bigquery.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com
```

### 2. BigQuery データセット作成

```bash
bq mk --location=asia-northeast1 YOUR_PROJECT_ID:fitbit_raw
bq mk --location=asia-northeast1 YOUR_PROJECT_ID:fitbit_mart
```

### 3. OAuth 2.0 クライアント作成と refresh token 取得

1. [Google Cloud Console](https://console.cloud.google.com/apis/credentials) で OAuth 2.0 クライアント ID を作成
   - アプリケーションの種類: **デスクトップ アプリ**
   - リダイレクト URI: `http://localhost:8080/callback`
2. クライアント ID とクライアントシークレットをメモ
3. 以下のスクリプトで refresh token を取得:

```bash
uv sync --only-group ingest
uv run python ingest/oauth_bootstrap.py \
  --client-id YOUR_CLIENT_ID \
  --client-secret YOUR_CLIENT_SECRET
# ブラウザが開くので認可 → refresh token が表示される
```

4. 表示された refresh token をメモ（GitHub Secrets に登録します）

### 4. Workload Identity Federation セットアップ

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export REPO=YOUR_GITHUB_USERNAME/pluse-board
export SA=fitbit-dashboard@${PROJECT_ID}.iam.gserviceaccount.com

# Service Account 作成
gcloud iam service-accounts create fitbit-dashboard \
  --display-name="pluse-board CI"

# BigQuery 権限付与
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA}" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA}" --role="roles/bigquery.jobUser"

# Workload Identity Pool 作成
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions Pool"

# GitHub OIDC Provider 作成
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global \
  --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'"

# SA にリポジトリからの借用を許可
gcloud iam service-accounts add-iam-policy-binding ${SA} \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"
```

### 5. GitHub Secrets / Variables 登録

リポジトリの **Settings → Secrets and variables → Actions** で以下を登録:

#### Secrets（機密情報）

| 名前 | 値 |
|---|---|
| `GOOGLE_HEALTH_CLIENT_ID` | OAuth クライアント ID |
| `GOOGLE_HEALTH_CLIENT_SECRET` | OAuth クライアントシークレット |
| `GOOGLE_HEALTH_REFRESH_TOKEN` | 手順 3 で取得した refresh token |

#### Variables（非機密の設定値）

| 名前 | 値 |
|---|---|
| `PROJECT_ID` | GCP プロジェクト ID（例: `my-project-123`） |
| `PROJECT_NUMBER` | GCP プロジェクト番号（数字のみ） |
| `BQ_DATASET_RAW` | raw データセット名（既定: `fitbit_raw`） |
| `BQ_DATASET_MART` | mart データセット名（既定: `fitbit_mart`） |
| `BQ_LOCATION` | BigQuery ロケーション（例: `asia-northeast1`） |

### 6. GitHub Pages 有効化

リポジトリの **Settings → Pages** で:
- Source: **GitHub Actions** を選択

> **注意**: 健康データを含むため、リポジトリは **Private** に設定してください（GitHub Pages は Pro プラン以上で Private リポジトリにも対応）。

---

## ローカル開発

### ingest 動作確認

```bash
# リポジトリルートで実行
uv sync --only-group ingest

# exercise データを取得して BigQuery にロード
uv run python ingest/pull_health_api.py --data-type exercise --start 2026-04-01
```

### dbt 動作確認

`dbt_project/profiles.yml` をテンプレート（`profiles.yml.example`）からコピーして作成してください。このファイルは gitignore 済みなのでリポジトリには含まれません。

```bash
cp dbt_project/profiles.yml.example dbt_project/profiles.yml
# YOUR_PROJECT_ID を実際の値に書き換える
```

事前に `gcloud auth application-default login` で認証してから:

```bash
# リポジトリルートで実行
uv sync --only-group dbt
cd dbt_project && uv run dbt deps && uv run dbt run
```

### Evidence 動作確認

```bash
cd reports
npm install
npm run sources   # BigQuery からデータを取得
npm run dev       # http://localhost:3000/pluse-board
```

---

## データフロー

| レイヤー | BigQuery データセット | 内容 |
|---|---|---|
| raw | `fitbit_raw` | Health API から取得したデータをそのまま格納 |
| mart | `fitbit_mart` | dbt で集計・変換したレポート用テーブル |

### raw テーブル

| テーブル | データタイプ | 説明 |
|---|---|---|
| `exercise` | `exercise` | 運動セッション（種別・時間） |
| `steps` | `steps` | 歩数 |
| `active_zone_minutes` | `active-zone-minutes` | アクティブゾーン分（ACWR 計算に使用） |

### mart テーブル

| テーブル | 説明 |
|---|---|
| `mart_exercise_daily` | 日次運動時間（種別ごと） |
| `mart_exercise_weekly` | 週次運動時間（種別ごと） |
| `mart_steps_daily` | 日次歩数 |
| `mart_load_daily` | 日次トレーニング負荷（AZM 合計） |
| `mart_acwr` | ACWR（Acute:Chronic Workload Ratio） |
