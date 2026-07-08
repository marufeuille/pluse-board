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

# --- 故意 FAIL ルール（学習用トグル） -------------------------------------
# 初回 apply では true にして「FAIL の見え方」を体感し、確認後 false にすると
# スキャンを削除せず正常系（全 PASS）に戻せる。
variable "include_demo_failing_rule" {
  description = "steps <= 10000 という現実に反する行条件ルールを含め、意図的に FAIL させる（学習用）"
  type        = bool
  default     = true
}

variable "demo_failing_steps_threshold" {
  description = "故意 FAIL ルールの上限。実測 max(steps)=19253 より小さくすると FAIL する。"
  type        = number
  default     = 10000
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
