variable "project_id" {
  description = "GCP プロジェクト ID"
  type        = string
  default     = "pluse-board"
}

variable "region" {
  description = "Dataplex / BigQuery のリージョン。DataScan はリージョナルなので対象データセットと一致させる。"
  type        = string
  default     = "asia-northeast1"
}

variable "mart_dataset" {
  description = "マート用 BigQuery データセット"
  type        = string
  default     = "fitbit_mart"
}

variable "scan_target_table" {
  description = "スキャン対象テーブル/ビュー名（fitbit_mart 内）。SQLMesh の prod マートは VIEW だが DataScan は VIEW でも動作する（検証済み）。"
  type        = string
  default     = "mart_steps_daily"
}

# --- スケジュール --------------------------------------------------------
# 品質スキャンはデイリー監視。cron は UTC。既定 "0 1 * * *" = 01:00 UTC = 10:00 JST
# （Daily Build は 00:00 UTC 開始なので、その後に走るよう 1 時間バッファ）。
# 対象が極小テーブルのため課金は月数円〜数十円で数ドルに届かない（README のコスト節参照）。
variable "quality_scan_cron" {
  description = "品質スキャンの実行スケジュール（unix-cron, UTC）"
  type        = string
  default     = "0 1 * * *"
}

# --- 結果公開 --------------------------------------------------------------
variable "enable_catalog_publishing" {
  description = "スキャン結果を Dataplex Catalog / BigQuery の品質・プロファイルタブに公開する"
  type        = bool
  default     = true
}

# --- IAM（追記型のみ・既定は付与しない） ----------------------------------
# AGENTS.md により IAM 変更は要承認。ローカル実行者は既に Owner 相当のため
# 既定では付与不要。CI SA へのロールは S3（CI 組込み）着手時に true にする。
variable "grant_ci_datascan_role" {
  description = "CI SA に roles/dataplex.dataScanEditor を追記付与する（S3 用。既定 false）"
  type        = bool
  default     = false
}

variable "ci_service_account" {
  description = "CI が借用する既存 SA（daily.yml の WIF 対象）"
  type        = string
  default     = "fitbit-dashboard@pluse-board.iam.gserviceaccount.com"
}
