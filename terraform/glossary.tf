# =====================================================================
# Story 5: ビジネスグロッサリ
#   技術メタデータ（スキーマ）とビジネス定義の橋渡し。
#   Glossary > Category > Term の階層でドメイン用語を定義し、
#   マート/ステージングのカラムへ「definition」エントリリンクで紐付ける。
#
#   TF 管理境界（S4 と同じ原則: 管理主体と操作手段を一致させる）:
#     - Glossary / Category / Term は TF 管理下（provider google v6.50 で対応）。
#     - カラムへの紐付け（EntryLink）は TF にも gcloud にもリソースが無く、
#       かつ実体は TF 管理外の system entry group `@bigquery` 配下に作られる。
#       → scripts/dataplex_glossary_links.sh（REST 直叩き）で作る。
#
#   定義の出どころは reports/pages/about.md。ダッシュボードの用語解説と
#   カタログの用語定義が二重管理になっている点は README の「学び」に記録した。
# =====================================================================

resource "google_dataplex_glossary" "health_metrics" {
  project     = var.project_id
  location    = var.region
  glossary_id = "health-metrics"

  display_name = "ヘルスメトリクス用語集 (S5)"
  description  = "トレーニング負荷・筋トレ継続まわりのドメイン用語。定義の原典は reports/pages/about.md。"

  labels = {
    purpose = "governance-learning"
    story   = "s5-glossary"
  }

  depends_on = [google_project_service.dataplex]
}

# --- カテゴリ ---------------------------------------------------------------
# ACWR は AZM ベースの心拍負荷、筋トレは頻度ベース。about.md で説明が分かれている
# 2 軸をそのままカテゴリにする。
resource "google_dataplex_glossary_category" "training_load" {
  project     = var.project_id
  location    = var.region
  glossary_id = google_dataplex_glossary.health_metrics.glossary_id
  category_id = "training-load"
  parent      = google_dataplex_glossary.health_metrics.name

  display_name = "トレーニング負荷"
  description  = "心拍ゾーン由来の負荷量と、その急性/慢性比で怪我リスクを測る系の用語。"
}

resource "google_dataplex_glossary_category" "strength_training" {
  project     = var.project_id
  location    = var.region
  glossary_id = google_dataplex_glossary.health_metrics.glossary_id
  category_id = "strength-training"
  parent      = google_dataplex_glossary.health_metrics.name

  display_name = "筋トレ継続"
  description  = "心拍が上がりきらず負荷に現れない筋トレを、頻度と連続達成で追う系の用語。"
}

# --- 用語 -------------------------------------------------------------------
resource "google_dataplex_glossary_term" "active_zone_minutes" {
  project     = var.project_id
  location    = var.region
  glossary_id = google_dataplex_glossary.health_metrics.glossary_id
  term_id     = "active-zone-minutes"
  parent      = google_dataplex_glossary_category.training_load.name

  display_name = "アクティブゾーン分 (AZM)"
  description  = "中〜高強度の心拍ゾーンに入っていた分数。Google Health API がゾーン別に返す生の強度指標で、トレーニング負荷の材料になる。"
}

resource "google_dataplex_glossary_term" "training_load" {
  project     = var.project_id
  location    = var.region
  glossary_id = google_dataplex_glossary.health_metrics.glossary_id
  term_id     = "training-load"
  parent      = google_dataplex_glossary_category.training_load.name

  display_name = "トレーニング負荷 (Load)"
  description  = "アクティブゾーン分の日次合計。運動しなかった日は 0（欠測ではない）として扱う。ACWR の入力。"
}

resource "google_dataplex_glossary_term" "acwr" {
  project     = var.project_id
  location    = var.region
  glossary_id = google_dataplex_glossary.health_metrics.glossary_id
  term_id     = "acwr"
  parent      = google_dataplex_glossary_category.training_load.name

  display_name = "ACWR (Acute:Chronic Workload Ratio)"
  description  = "直近 7 日の平均日次負荷 ÷ 直近 28 日の平均日次負荷。0.8–1.3 が適切ゾーン、1.5 超は過負荷で怪我リスクが高い、0.8 未満は負荷不足。28 日窓が揃わない初期データは NULL。"
}

resource "google_dataplex_glossary_term" "strength_target" {
  project     = var.project_id
  location    = var.region
  glossary_id = google_dataplex_glossary.health_metrics.glossary_id
  term_id     = "strength-target"
  parent      = google_dataplex_glossary_category.strength_training.name

  display_name = "筋トレ達成週"
  description  = "週の筋トレセッション数が 3 回以上である週。週はじまりは日曜。筋トレ 0 回の週も 0 埋めするため、サボった週でストリークが正しく途切れる。"
}
