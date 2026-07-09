# terraform/ — pluse-board 初の IaC（Dataplex ガバナンス）

このリポジトリ初の Infrastructure-as-Code。Dataplex の
**データプロファイルスキャン（S1）**・**データ品質スキャン（S2）**（`datascans.tf`）、
**カタログエントリ＋アスペクト（S4）**（`catalog.tf`）、
**ビジネスグロッサリ（S5）**（`glossary.tf`）を管理する。
以降のストーリー（S6）で拡張していく。設計とストーリー全体は
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

# 3. 適用（API 有効化 + DataScan 2 本 + Entry Group / Aspect Type / Entry 3 本
#          + Glossary 1 / Category 2 / Term 4）
terraform apply

# 4. スキャン実行（どちらも on_demand）
#    - 品質スキャン: 通常は Daily Build（daily.yml）が SQLMesh run 直後に起動する
#    - プロファイル: ベースライン更新時に手動実行
terraform output run_commands
gcloud dataplex datascans run mart-steps-daily-profile --location=asia-northeast1 --project=pluse-board
# 品質を手元から即時に走らせたいとき（CI を待たずに）
gcloud dataplex datascans run mart-steps-daily-quality --location=asia-northeast1 --project=pluse-board

# 5. カタログの確認（S4）
terraform output catalog_search_commands

# 6. 用語をカラムに紐付ける（S5。terraform apply だけでは紐付かない）
terraform output glossary_link_commands
cd .. && ./scripts/dataplex_glossary_links.sh
```

## トリガー

| スキャン | トリガー | 備考 |
|---|---|---|
| プロファイル (S1) | `on_demand` | ベースライン用途。都度手動実行 |
| 品質 (S2) | `on_demand` | Daily Build が SQLMesh run 直後に起動（S3）。新鮮なデータの直後に同期判定し FAIL を beads/Slack へ |

> Dataplex 側のデイリースケジュールは S3 で撤去した。CI から起動すれば「取り込み → 変換 → 品質判定」が
> 1 本のパイプラインに収まり、結果を既存の通知基盤に流せる。両方あると二重実行になる。

## 変数（`terraform.tfvars`）

| 変数 | 既定 | 意味 |
|---|---|---|
| `enable_catalog_publishing` | `true` | 品質結果を Catalog / BigQuery「データ品質」タブに公開 |
| `catalog_data_owner` | `marufeuille@gmail.com` | S4 の台帳アスペクト `data_owner` に入れる管理責任者 |
| `grant_ci_datascan_role` | `true` | CI SA に `dataScanEditor` + `dataScanDataViewer` を**追記**付与（S3 の CI 連携に必須） |

## S5: 用語をカラムに紐付ける（`scripts/dataplex_glossary_links.sh`）

`glossary.tf` は Glossary / Category / Term までしか作れない。**用語↔カラムの紐付けは
「definition タイプの EntryLink」**という別リソースで、Terraform provider にも gcloud にも存在せず
REST API しか経路が無い。しかも実体は Dataplex が自動生成する `@bigquery` エントリグループ配下
（= TF 管理外）に作られる。S4 のアスペクト付与と同じ理屈で、TF ではなくスクリプトで管理する。

```bash
./scripts/dataplex_glossary_links.sh           # 不足しているリンクを作る（冪等）
./scripts/dataplex_glossary_links.sh --verify  # 用語側から逆引きして確認
./scripts/dataplex_glossary_links.sh --delete  # 作ったリンクを削除
```

紐付け対象はスクリプト内の `LINKS` 配列に `<dataset>:<table>:<column>:<term_id>` で持つ。
用語の定義そのものは `glossary.tf`、定義の原典は [`../reports/pages/about.md`](../reports/pages/about.md)。

## S4: `@bigquery` エントリへのアスペクト付与（手動 runbook）

`catalog.tf` が作る 3 つのカスタムエントリには Terraform の `aspects` ブロックでアスペクトが付く。
一方 **BigQuery のエントリは Dataplex が `@bigquery` エントリグループに自動生成する TF 管理外リソース**で、
`google_dataplex_entry` では管理できない。こちらへの付与は gcloud で一度だけ行う。

```bash
# 1. エントリ ID はフルリソースパス形式（DATASET.TABLE ではない）
ENTRY="projects/pluse-board/locations/asia-northeast1/entryGroups/@bigquery/entries/bigquery.googleapis.com/projects/pluse-board/datasets/fitbit_mart/tables/mart_steps_daily"

# 2. アスペクトキーはプロジェクト「番号」表記（terraform output governance_aspect_key）
cat > aspects.json <<'JSON'
{
  "274885157237.asia-northeast1.governance-metadata": {
    "data": { "data_owner": "marufeuille@gmail.com", "update_frequency": "DAILY", "sensitivity": "HEALTH" }
  }
}
JSON

# 3. 付与（update-aspects は既存アスペクトを保ったままマージする）
gcloud dataplex entries update-aspects "$ENTRY" --aspects=aspects.json
gcloud dataplex entries describe "$ENTRY" --view=ALL --format="value(aspects)"
```

TF 管理下は TF、管理外は gcloud —— 管理境界と操作手段が一致しているので drift しない
（S1 でプロファイルの `--enable-catalog-publishing` を見送ったのは、TF 管理下のリソースに
gcloud で設定を足すと drift するからだった。今回は事情が違う）。

## IAM の方針（重要）

- **追記型 `google_project_iam_member` のみ**。権威型（`google_project_iam_policy` /
  `google_project_iam_binding`）は既存の WIF/BigQuery バインディングを破壊するため**使わない**。
- ローカル実行者は Owner 相当のため付与不要。CI SA には 2 ロールが要る:
  - `roles/dataplex.dataScanEditor` — スキャンの起動
  - `roles/dataplex.dataScanDataViewer` — ジョブ結果（`dataQualityResult`）の閲覧。**Editor だけでは
    合否・スコアが読めない**（job は GET できるが結果本体が返らない）

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
# 先に TF 管理外のものを消す（destroy では消えない）
./scripts/dataplex_glossary_links.sh --delete

terraform destroy   # DataScan / Entry Group / Aspect Type / Entry / Glossary 一式を削除
                    # （dataplex API は disable_on_destroy=false のため無効化しない）
```

`terraform destroy` は **`@bigquery` エントリに gcloud で足したアスペクトを消さない**（TF 管理外のため）。
必要なら別途:

```bash
gcloud dataplex entries modify "$ENTRY" --remove-aspects=274885157237.asia-northeast1.governance-metadata
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

一方 **S4 のカタログエントリ／アスペクトと S5 のグロッサリは DCU を消費しない**（DataScan と違い
compute が走らない）。課金対象はメタデータストレージのみで、エントリ数本・数百バイトのアスペクト・
用語 4 本では実質 **$0**。
