# IAM は【追記型 google_project_iam_member のみ】。
# 権威型 google_project_iam_policy / google_project_iam_binding は既存の
# WIF/BigQuery バインディングを破壊するため絶対に使わない（AGENTS.md 準拠）。
#
# ローカル実行者（marufeuille）は既に Owner 相当のため付与不要。
# CI SA には S3（daily.yml から DataScan を起動し合否を判定する）のため 2 ロールが要る:
#   - dataScanEditor    : スキャンの起動（dataplex.datascans.run）とジョブのメタデータ取得
#   - dataScanDataViewer: ジョブ結果の中身（dataQualityResult = 合否・スコア・ルール別内訳）の閲覧
# Editor だけでは job を GET できても dataQualityResult が返らず合否判定ができない。
resource "google_project_iam_member" "ci_datascan_editor" {
  count   = var.grant_ci_datascan_role ? 1 : 0
  project = var.project_id
  role    = "roles/dataplex.dataScanEditor"
  member  = "serviceAccount:${var.ci_service_account}"
}

resource "google_project_iam_member" "ci_datascan_data_viewer" {
  count   = var.grant_ci_datascan_role ? 1 : 0
  project = var.project_id
  role    = "roles/dataplex.dataScanDataViewer"
  member  = "serviceAccount:${var.ci_service_account}"
}
