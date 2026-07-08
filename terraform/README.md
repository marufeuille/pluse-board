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

# 4. スキャンを手動実行（on_demand トリガー）
#    apply 後に出力される run_commands を使う
terraform output run_commands
gcloud dataplex datascans run mart-steps-daily-profile --location=asia-northeast1 --project=pluse-board
gcloud dataplex datascans run mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board
```

## 学習用トグル（`terraform.tfvars`）

| 変数 | 既定 | 意味 |
|---|---|---|
| `include_demo_failing_rule` | `true` | `steps <= 10000`（実測 max=19253 に反する）で**故意に FAIL** させ、FAIL の見え方を体感 |
| `demo_failing_steps_threshold` | `10000` | 故意 FAIL ルールの上限 |
| `enable_catalog_publishing` | `true` | 品質結果を Catalog / BigQuery「データ品質」タブに公開 |
| `grant_ci_datascan_role` | `false` | CI SA に `roles/dataplex.dataScanEditor` を**追記**付与（S3 用） |

故意 FAIL を確認したら:

```bash
echo 'include_demo_failing_rule = false' >> terraform.tfvars
terraform apply     # ルールを削除（スキャン自体は残る）
gcloud dataplex datascans run mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board
```

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

## コスト注意

Dataplex DataScan は lineage 同様 **DCU 課金・無料枠なし**。対象 1 テーブル + on_demand なら実測は極小想定だが、
既存の予算アラート（`1000JPY`）が効いていることを確認すること。課金 SKU は Cloud Billing で
`goog-dataplex-workload-type` 系ラベルを数日観察する。
