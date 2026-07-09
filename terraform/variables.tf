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

# --- 結果公開 --------------------------------------------------------------
variable "enable_catalog_publishing" {
  description = "スキャン結果を Dataplex Catalog / BigQuery の品質・プロファイルタブに公開する"
  type        = bool
  default     = true
}

# --- カタログ（S4） --------------------------------------------------------
variable "catalog_data_owner" {
  description = "Catalog アスペクト data_owner に入れる管理責任者（メール / チーム）"
  type        = string
  default     = "marufeuille@gmail.com"
}

# --- IAM（追記型のみ） -----------------------------------------------------
# AGENTS.md により IAM 変更は要承認。ローカル実行者は既に Owner 相当のため付与不要だが、
# S3 で CI SA が DataScan を起動し結果を読むため、ユーザー承認のうえ既定 true にした。
variable "grant_ci_datascan_role" {
  description = "CI SA に DataScan の起動/結果閲覧ロールを追記付与する（S3 の daily.yml 連携に必須）"
  type        = bool
  default     = true
}

variable "ci_service_account" {
  description = "CI が借用する既存 SA（daily.yml の WIF 対象）"
  type        = string
  default     = "fitbit-dashboard@pluse-board.iam.gserviceaccount.com"
}
