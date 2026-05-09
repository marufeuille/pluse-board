# Fitbit データ可視化ダッシュボード 構築プラン

## 目的

Fitbitに蓄積したデータを継続的に可視化するダッシュボードを構築する。

### 可視化したい内容

- 日次の運動時間（筋トレ / ウォーキング等の種別ごと）
- 週次・月次での推移比較
- ACWR（Acute:Chronic Workload Ratio）の可視化
- 歩数の推移

## アーキテクチャ

```
Google Health API (REST)
        ↓  Python (日次取得)
BigQuery (raw layer)
        ↓  dbt-bigquery
BigQuery (mart layer)
        ↑
GitHub Actions (WIF で SA 借用)
        ↓  Evidence build
GitHub Pages
```

すべて GitHub リポジトリ1つに収まり、ビルド時に静的サイトを生成して GitHub Pages に公開する。

## 技術スタック

| レイヤー | 採用技術 | 補足 |
|---|---|---|
| データソース | Google Health API | Fitbit Web API は2026年9月廃止予定なので最初から後継APIで構築 |
| 認証 | Google OAuth 2.0 + WIF | refresh token は GitHub Secrets、CIは Workload Identity Federation |
| ストレージ | BigQuery | 個人データ規模なら無料枠で十分 |
| 変換 | dbt-bigquery | staging → marts |
| 可視化 | Evidence.dev | SQL + Markdown でダッシュボード、ビルド時に静的化 |
| ホスティング | GitHub Pages | Evidence 公式サポート |
| スケジュール | GitHub Actions | 日次 cron |

## Google Health API

### スコープ

```
https://www.googleapis.com/auth/googlehealth.activity_and_fitness
```

これ1つで運動・歩数・AZM すべてカバーできる。

### 取得対象データタイプ

| 要件 | データタイプ | エンドポイント |
|---|---|---|
| 運動時間（種類別） | `exercise` | `/v4/users/me/dataTypes/exercise/dataPoints` |
| 歩数推移 | `steps` | `/v4/users/me/dataTypes/steps/dataPoints` |
| ACWR用ロード | `active-zone-minutes` | `/v4/users/me/dataTypes/active-zone-minutes/dataPoints` |

注意: エンドポイントでは kebab-case (`active-zone-minutes`)、フィルタでは snake_case (`active_zone_minutes`)。

### リクエスト例

```http
GET https://health.googleapis.com/v4/users/me/dataTypes/exercise/dataPoints
    ?filter=exercise.interval.civil_start_time >= "2026-04-01T00:00:00"
Authorization: Bearer {{accessToken}}
Accept: application/json
```

### 移行スケジュール上の注意

- 2026年5月末まではAPIにブレイキングチェンジが入る可能性あり
- 本番運用は6月以降推奨、または APIラッパー層を薄く作って差し替え可能にしておく

## ディレクトリ構成

```
fitbit-dashboard/
├── ingest/
│   ├── pull_health_api.py        # Google Health API → BigQuery
│   └── requirements.txt
├── dbt_project/
│   ├── models/
│   │   ├── staging/
│   │   └── marts/
│   │       ├── mart_exercise_daily.sql
│   │       ├── mart_exercise_weekly.sql
│   │       ├── mart_steps_daily.sql
│   │       ├── mart_load_daily.sql
│   │       └── mart_acwr.sql
│   ├── dbt_project.yml
│   └── profiles.yml
├── reports/                       # Evidence プロジェクト
│   ├── pages/
│   │   ├── index.md
│   │   ├── exercise.md
│   │   └── acwr.md
│   ├── sources/bq/
│   │   └── connection.yaml
│   ├── evidence.config.yaml
│   └── package.json
└── .github/workflows/
    └── daily.yml
```

## dbt モデル設計

### `mart_exercise_daily.sql`

```sql
SELECT
  DATE(interval_civil_start_time) AS activity_date,
  activity_name,
  SUM(TIMESTAMP_DIFF(
       interval_civil_end_time,
       interval_civil_start_time, MINUTE)) AS duration_minutes
FROM {{ source('fitbit_raw', 'exercise') }}
GROUP BY 1, 2
```

### `mart_exercise_weekly.sql`

```sql
SELECT
  DATE_TRUNC(activity_date, WEEK(MONDAY)) AS week_start,
  activity_name,
  SUM(duration_minutes) AS duration_minutes
FROM {{ ref('mart_exercise_daily') }}
GROUP BY 1, 2
```

月次も同様に `MONTH` で。

### `mart_acwr.sql`

ACWR = 直近7日の平均日次負荷 ÷ 直近28日の平均日次負荷。
休養日を0で埋めないと過大評価になるため、calendar JOIN を必ず入れる。

```sql
WITH daily_load AS (
  SELECT
    DATE(interval_civil_start_time) AS d,
    SUM(value) AS load
  FROM {{ source('fitbit_raw', 'active_zone_minutes') }}
  GROUP BY 1
),
calendar AS (
  SELECT d FROM UNNEST(GENERATE_DATE_ARRAY(
    (SELECT MIN(d) FROM daily_load),
    CURRENT_DATE()
  )) AS d
),
filled AS (
  SELECT c.d, COALESCE(dl.load, 0) AS load
  FROM calendar c LEFT JOIN daily_load dl USING (d)
)
SELECT
  d,
  load,
  AVG(load) OVER (ORDER BY d ROWS BETWEEN 6  PRECEDING AND CURRENT ROW) AS acute_7d,
  AVG(load) OVER (ORDER BY d ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS chronic_28d,
  SAFE_DIVIDE(
    AVG(load) OVER (ORDER BY d ROWS BETWEEN 6  PRECEDING AND CURRENT ROW),
    AVG(load) OVER (ORDER BY d ROWS BETWEEN 27 PRECEDING AND CURRENT ROW)
  ) AS acwr
FROM filled
```

可視化時は 0.8〜1.3 を緑、>1.5 を赤の閾値ラインとして引く。

## Evidence ページ例

### `reports/pages/exercise.md`

`````markdown
# 運動の推移

```sql daily_exercise
SELECT activity_date, activity_name, duration_minutes
FROM bq.mart_exercise_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 90 DAY
```

<BarChart 
  data={daily_exercise} 
  x=activity_date 
  y=duration_minutes 
  series=activity_name 
  type=stacked 
  title="日次運動時間（種別ごと）"
/>

## 週次比較

```sql weekly
SELECT date_trunc('week', activity_date) AS week, 
       activity_name, 
       sum(duration_minutes) AS minutes
FROM bq.mart_exercise_daily 
GROUP BY 1, 2
```

<BarChart data={weekly} x=week y=minutes series=activity_name />
`````

### Evidence の BigQuery 接続

`reports/sources/bq/connection.yaml`:

```yaml
type: bigquery
name: bq
options:
  project_id: ${PROJECT_ID}
  authenticator: gcloud-cli
```

`google-github-actions/auth@v2` が ADC を仕込むので、Evidence の BigQuery コネクタは `gcloud-cli` モードで素直に拾う。`GOOGLE_APPLICATION_CREDENTIALS` 系の小細工は不要。

### Base path 設定

GitHub Pages はサブパス配信なので必須:

```yaml
# evidence.config.yaml
deployment:
  basePath: /fitbit-dashboard
```

## Workload Identity Federation セットアップ

一度きりの作業（10分程度）。長期キーをリポジトリに置かない。

```bash
# 1. SA 作成
gcloud iam service-accounts create fitbit-dashboard \
  --display-name="Fitbit Dashboard CI"

SA="fitbit-dashboard@${PROJECT_ID}.iam.gserviceaccount.com"

# 2. 権限付与
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA}" --role="roles/bigquery.dataEditor"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SA}" --role="roles/bigquery.jobUser"

# 3. Workload Identity Pool + GitHub OIDC Provider
gcloud iam workload-identity-pools create github-pool \
  --location=global

gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=github-pool \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='YOUR_USER/fitbit-dashboard'"

# 4. SA にリポジトリからの借用を許可
gcloud iam service-accounts add-iam-policy-binding ${SA} \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/YOUR_USER/fitbit-dashboard"
```

## GitHub Actions ワークフロー

`.github/workflows/daily.yml`:

```yaml
name: Daily Build
on:
  schedule: [{ cron: "0 18 * * *" }]   # 毎日 03:00 JST
  workflow_dispatch:

permissions:
  id-token: write   # WIF の鍵
  contents: read
  pages: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/${{ vars.PROJECT_NUMBER }}/locations/global/workloadIdentityPools/github-pool/providers/github
          service_account: fitbit-dashboard@${{ vars.PROJECT_ID }}.iam.gserviceaccount.com

      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }

      - name: Ingest from Health API
        env:
          GOOGLE_HEALTH_CLIENT_ID: ${{ secrets.GOOGLE_HEALTH_CLIENT_ID }}
          GOOGLE_HEALTH_CLIENT_SECRET: ${{ secrets.GOOGLE_HEALTH_CLIENT_SECRET }}
          GOOGLE_HEALTH_REFRESH_TOKEN: ${{ secrets.GOOGLE_HEALTH_REFRESH_TOKEN }}
        run: |
          pip install -r ingest/requirements.txt
          python ingest/pull_health_api.py

      - name: dbt
        run: |
          pip install dbt-bigquery
          cd dbt_project && dbt run

      - uses: actions/setup-node@v4
        with: { node-version: "20" }

      - name: Build Evidence
        working-directory: reports
        run: |
          npm ci
          npm run sources   # ← BQ クエリ実行（ビルド時1回）
          npm run build

      - uses: actions/upload-pages-artifact@v3
        with: { path: reports/build }

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: github-pages
    steps:
      - uses: actions/deploy-pages@v4
```

## ハマりどころ

1. **Health API の OAuth 認可フロー（初回のみ）**
   ローカルでブラウザ認可フローを回して refresh token 取得 → GitHub Secrets に格納。
   アクセストークンは1時間で切れるので、毎回 refresh token から再発行する処理を `pull_health_api.py` に実装。

2. **kebab-case / snake_case の使い分け**
   エンドポイント URL では kebab-case、filter パラメータでは snake_case。Health API 全体で共通の地味な落とし穴。

3. **ACWR 計算で休養日を0埋めし忘れる**
   運動した日だけで rolling 平均を取ると ACWR が過大評価される。calendar table JOIN は必須。

4. **Evidence の base path**
   GitHub Pages のサブパス配信に合わせないと CSS と画像が全部 404 する。

5. **プライバシー**
   GitHub Pages は原則公開。健康データを公開したくないなら Private repo + GitHub Pages（Pro 以上）か、別の認証付きホスティングを検討。

## 進め方の順序

1. Google Cloud プロジェクト作成 → Health API 有効化 → OAuth 2.0 クライアント作成（公式 codelab 推奨）
2. ローカルで `exercise` エンドポイントを1つだけ叩いてレスポンス構造確認
3. WIF セットアップ
4. Python ingest スクリプトで3データタイプを BigQuery に投入
5. dbt で `mart_exercise_daily` 1つだけ作って動作確認
6. Evidence で運動時間グラフ → ここで要件①②達成
7. AZM 追加 → `mart_acwr` → ACWR グラフ
8. GitHub Actions で日次スケジュール化
9. GitHub Pages デプロイ

## 次のステップ候補

- [ ] `pull_health_api.py` のフル実装（OAuth refresh 含む）
- [ ] dbt-bigquery の `profiles.yml` + 全モデル
- [ ] Evidence のページ3つ分（運動・歩数・ACWR）一式

