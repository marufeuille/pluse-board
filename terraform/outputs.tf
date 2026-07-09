output "profile_scan_id" {
  description = "プロファイルスキャンの data_scan_id"
  value       = google_dataplex_datascan.mart_steps_profile.data_scan_id
}

output "quality_scan_id" {
  description = "品質スキャンの data_scan_id"
  value       = google_dataplex_datascan.mart_steps_quality.data_scan_id
}

output "run_commands" {
  description = "スキャンを手動実行するコマンド（on_demand トリガー）"
  value = {
    profile = "gcloud dataplex datascans run ${google_dataplex_datascan.mart_steps_profile.data_scan_id} --location=${var.region} --project=${var.project_id}"
    quality = "gcloud dataplex datascans run ${google_dataplex_datascan.mart_steps_quality.data_scan_id} --location=${var.region} --project=${var.project_id}"
  }
}

output "entry_group_id" {
  description = "Health API 外部ソースの Entry Group ID (S4)"
  value       = google_dataplex_entry_group.googlehealth.entry_group_id
}

output "governance_aspect_key" {
  description = "アスペクトキー（API / TF / gcloud update-aspects 用。プロジェクト番号表記）(S4)"
  value       = local.governance_aspect_key
}

# 注意: search 述語のアスペクト参照はプロジェクト「ID」表記（projectid.location.aspect_type_id）。
# API 側の aspect_key（プロジェクト番号表記）を渡すと 0 件になる。実測で確認済み。
output "catalog_search_commands" {
  description = "Catalog search で属性検索を確認するコマンド（search はグローバル集約）"
  value = {
    by_sensitivity = "gcloud dataplex entries search 'aspect:${google_dataplex_aspect_type.governance.aspect_type_id}.sensitivity=HEALTH' --project=${var.project_id}"
    by_aspect      = "gcloud dataplex entries search 'aspect=${var.project_id}.${var.region}.${google_dataplex_aspect_type.governance.aspect_type_id}' --project=${var.project_id}"
    by_keyword     = "gcloud dataplex entries search 'googlehealth' --project=${var.project_id}"
  }
}
