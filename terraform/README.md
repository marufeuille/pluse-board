# terraform/ — pluse-board 初の IaC（Dataplex ガバナンス）

このリポジトリ初の Infrastructure-as-Code。まずは Dataplex の
**データプロファイルスキャン（S1）** と **データ品質スキャン（S2）** のみを管理する。
以降のストーリー（S3–S6）で拡張していく。設計とストーリー全体は
[`../docs/dataplex-governance-stories.md`](../docs/dataplex-governance-stories.md) を参照。

## 前提

- `terraform >= 1.5`、`google` provider `~> 6.0`
- 認証は **ADC**: `gcloud auth application-default login`（実行者は Dataplex/BQ 権限が必要。Owner なら十分）
- `dataplex.googleapis.com` は API 経由で有効化される（既に有効でも冪等）
- 対象は `pluse-board` / `asia-northeast1` の `fitbit_mart.mart_steps_daily`

> **学び**: DataScan の対象は「BigQuery テーブル/Iceberg テーブルのみ」とドキュメントにあるが、
> 実地検証では **SQLMesh が公開する VIEW（`fitbit_mart.mart_steps_daily`）でもプロファイル/品質スキャンとも動作した**。
> SQLMesh は全モデルを仮想レイヤの VIEW として公開するため、この点は本パイプラインをガバナンスするうえで重要。

## 使い方

```bash
cd terraform

# 1. 初期化（provider 取得）
terraform init

# 2. 差分確認（何が作られるか）
terraform plan

# 3. 適用（API 有効化 + DataScan 2 本を作成）
terraform apply

# 4. スキャン実行
#    - 品質スキャン: デイリースケジュール（既定 10:00 JST）で自動実行される
#    - プロファイル: on_demand。ベースライン更新時に手動実行
terraform output run_commands
gcloud dataplex datascans run mart-steps-daily-profile --location=asia-northeast1 --project=pluse-board
# 品質を即時に走らせたいとき（スケジュールを待たずに）
gcloud dataplex datascans run mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board
```

## トリガー

| スキャン | トリガー | 備考 |
|---|---|---|
| プロファイル (S1) | `on_demand` | ベースライン用途。都度手動実行 |
| 品質 (S2) | `schedule`（既定 `0 1 * * *` = 10:00 JST） | デイリー監視。Daily Build（00:00 UTC）の後に走るよう 1h バッファ |

## 変数（`terraform.tfvars`）

| 変数 | 既定 | 意味 |
|---|---|---|
| `quality_scan_cron` | `"0 1 * * *"` | 品質スキャンのデイリー実行 cron（UTC。10:00 JST） |
| `enable_catalog_publishing` | `true` | 品質結果を Catalog / BigQuery「データ品質」タブに公開 |
| `grant_ci_datascan_role` | `false` | CI SA に `roles/dataplex.dataScanEditor` を**追記**付与（S3 用） |

## IAM の方針（重要）

- **追記型 `google_project_iam_member` のみ**。権威型（`google_project_iam_policy` /
  `google_project_iam_binding`）は既存の WIF/BigQuery バインディングを破壊するため**使わない**。
- ローカル実行者は Owner 相当のため DataScan ロールは付与不要（既定で IAM は変更しない）。

## backend（state）

現状は **local backend**（`terraform.tfstate` はローカルのみ・`.gitignore` 済み）。
チーム化や再現性が必要になったら **GCS backend** へ移行する（学習課題）:

```bash
# 1. state バケットを作成（バージョニング推奨）
gsutil mb -l asia-northeast1 gs://pluse-board-tfstate
gsutil versioning set on gs://pluse-board-tfstate

# 2. versions.tf に backend ブロックを追加
#    backend "gcs" { bucket = "pluse-board-tfstate" prefix = "dataplex" }

# 3. 既存 local state を移行
terraform init -migrate-state
```

## 後片付け

`on_demand` トリガーなので放置課金は最小。学習が済んだらスキャンを削除:

```bash
terraform destroy   # DataScan を削除（dataplex API は disable_on_destroy=false のため無効化しない）
```

## コスト

Dataplex DataScan は premium processing = **$0.089/DCU-hour・無料枠なし**、**秒課金・最低1分**。
消費 DCU は行数×列数×スキャン量に比例する。対象 `mart_steps_daily` は 98 行×2 列と極小なので
1 回のスキャンは実質「最低 1 分」に張り付く:

- 1 スキャン ≈ 0.017 DCU-hour ≈ **$0.0015（≒0.2 円）/回**
- 品質を毎日 1 回 × 30 日 ≈ **月 $0.05 未満（数円〜十数円）**。実消費が数倍でも月 $1 未満。

→ 数ドルには全く届かないのでデイリー実行で問題ない。ただし premium は無料枠対象外なので厳密には $0 ではない。
既存の予算アラート（`1000JPY`）が効いていることを確認し、課金 SKU は Cloud Billing で
`goog-dataplex-workload-type` 系ラベルを数日観察する。
