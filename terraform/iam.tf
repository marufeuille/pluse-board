# IAM は【追記型 google_project_iam_member のみ】。
# 権威型 google_project_iam_policy / google_project_iam_binding は既存の
# WIF/BigQuery バインディングを破壊するため絶対に使わない（AGENTS.md 準拠）。
#
# ローカル実行者（marufeuille）は既に Owner 相当のため DataScan ロールは付与不要。
# CI SA へのロールは S3（CI 組込み）着手時に grant_ci_datascan_role=true で有効化する。
# 既定 false = このターンでは IAM を一切変更しない。
resource "google_project_iam_member" "ci_datascan_editor" {
  count   = var.grant_ci_datascan_role ? 1 : 0
  project = var.project_id
  role    = "roles/dataplex.dataScanEditor"
  member  = "serviceAccount:${var.ci_service_account}"
}
