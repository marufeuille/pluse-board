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
