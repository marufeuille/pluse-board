# Dataplex API。既に手動で有効化済みでも apply は冪等（既存有効化を state に取り込むだけ）。
# disable_on_destroy=false: terraform destroy でも API は無効化しない（他機能への巻き添え防止）。
resource "google_project_service" "dataplex" {
  project            = var.project_id
  service            = "dataplex.googleapis.com"
  disable_on_destroy = false
}
