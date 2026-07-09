# =====================================================================
# Story 4: カタログエントリ＋アスペクト
#   (a) lineage の外部参照ノード custom:googlehealth:activity/* を、FQN が一致する
#       Entry として登録し「一級カタログエントリ」化する（Entry Group + Entry）。
#       lineage は辺を描くために FQN を参照するだけでエントリ実体を作らない。
#       FQN が一致した Entry を後から作ると、lineage グラフの外部ノードが実体に解決される。
#   (b) Aspect Type（data_owner / update_frequency / sensitivity）を定義し、
#       上記 Entry に付与する＝メタデータ台帳。
#
#   注意（provider の仕様）:
#     - Entry 系リソースの project は「プロジェクト ID ではなく番号」を要求される。
#       アスペクトキーも {project_number}.{location}.{aspect_type_id} 形式。
#       → data.google_project.this.number に統一する。
#     - metadata_template の record 名 / field 名はハイフン不可（アンダースコア）。
#       一方リソース ID（aspect_type_id）はハイフン可。両者を混同しない。
#
#   TF 管理境界: ここで作る 3 エントリは TF 管理下なのでアスペクトも TF で付ける。
#   既存 BigQuery エントリ（Dataplex が @bigquery に自動生成）は TF 管理外なので
#   gcloud で付与する（terraform/README.md の runbook）。管理境界と操作手段が
#   一致しているため drift しない。
# =====================================================================

data "google_project" "this" {}

locals {
  # Entry 系はプロジェクト「番号」を使う（provider 仕様）。
  project_number = data.google_project.this.number

  # ingest/lineage.py が emit する外部ソースの data_type と厳密に一致させる。
  # （ingest/pull_health_api.py の ENABLED_DATA_TYPES）
  health_data_types = toset(["exercise", "steps", "active_zone_minutes"])

  # アスペクトキー: {project_number}.{location}.{aspect_type_id}
  governance_aspect_key = "${local.project_number}.${var.region}.${google_dataplex_aspect_type.governance.aspect_type_id}"

  # システム定義の再利用可能な Entry Type。restricted 型（bigquery-table 等）は
  # Google Cloud リソース専用でカスタムエントリには使えない。
  # provider は entry_type にもプロジェクト「番号」を要求するため、Google 側の
  # 固定プロジェクト dataplex-types を ID ではなく番号 655216118709 で書く
  # （gcloud は ID 表記を返すが terraform validate は ID を弾く）。
  system_entry_type_generic = "projects/655216118709/locations/global/entryTypes/generic"

  # generic Entry Type は同名の generic Aspect Type を requiredAspects に持つ。
  # 付けずに作ると API が 400 "Missing required Aspect(s)" を返す。
  # location は global（アスペクトキーの第 2 要素は Aspect Type 側のロケーション）。
  generic_aspect_key = "655216118709.global.generic"
}

# --- (a) 外部ソースの入れ物 -------------------------------------------------
# location は lineage の投入先（locations/${BQ_LOCATION}）および @bigquery の
# 自動生成エントリと揃える。Catalog search はグローバル集約なので検索性は落ちない。
resource "google_dataplex_entry_group" "googlehealth" {
  project        = local.project_number
  location       = var.region
  entry_group_id = "googlehealth-sources"
  display_name   = "Google Health API 外部ソース (S4)"
  description    = "lineage の外部参照ノード custom:googlehealth:* を一級カタログエントリ化するための Entry Group。"

  labels = {
    purpose = "governance-learning"
    story   = "s4-catalog"
  }

  depends_on = [google_project_service.dataplex]
}

# --- (b) 構造化メタデータ型（台帳カード 1 枚 = 1 アスペクト） -----------------
# data_owner / update_frequency / sensitivity を 1 つの record にまとめる。
# 3 つの Aspect Type に分割する案もあるが、本リポでは全対象が sensitivity=HEALTH の
# ため粒度を分ける実益が薄い。
resource "google_dataplex_aspect_type" "governance" {
  project        = local.project_number
  location       = var.region
  aspect_type_id = "governance-metadata"
  display_name   = "ガバナンスメタデータ (S4)"
  description    = "data_owner / update_frequency / sensitivity の台帳アスペクト。"

  labels = {
    purpose = "governance-learning"
    story   = "s4-catalog"
  }

  metadata_template = jsonencode({
    name = "governance_metadata"
    type = "record"
    recordFields = [
      {
        name        = "data_owner"
        type        = "string"
        index       = 1
        constraints = { required = true }
        annotations = {
          displayName = "Data Owner"
          description = "データの管理責任者（メール / チーム）"
        }
      },
      {
        name  = "update_frequency"
        type  = "enum"
        index = 2
        annotations = {
          displayName = "Update Frequency"
          description = "更新頻度"
        }
        enumValues = [
          { name = "DAILY", index = 1 },
          { name = "WEEKLY", index = 2 },
          { name = "MONTHLY", index = 3 },
          { name = "ON_DEMAND", index = 4 },
        ]
      },
      {
        name        = "sensitivity"
        type        = "enum"
        index       = 3
        constraints = { required = true }
        annotations = {
          displayName = "Sensitivity"
          description = "データ機微区分。健康データは HEALTH（PII の一種）。"
        }
        enumValues = [
          { name = "HEALTH", index = 1 },
          { name = "PII", index = 2 },
          { name = "INTERNAL", index = 3 },
          { name = "PUBLIC", index = 4 },
        ]
      },
    ]
  })

  depends_on = [google_project_service.dataplex]
}

# --- (a)+(b) 外部ソースを FQN 一致の Entry として登録し、アスペクトを付与 -------
resource "google_dataplex_entry" "googlehealth_activity" {
  for_each = local.health_data_types

  project        = local.project_number
  location       = var.region
  entry_group_id = google_dataplex_entry_group.googlehealth.entry_group_id
  entry_id       = "activity-${each.key}"

  entry_type = local.system_entry_type_generic

  # lineage ノードとリンクさせる肝。ingest/lineage.py の namespace/name と厳密一致。
  # （namespace="custom" + name="googlehealth:activity/<data_type>"）
  fully_qualified_name = "custom:googlehealth:activity/${each.key}"

  entry_source {
    display_name = "Google Health API — activity/${each.key}"
    description  = "Health API の ${each.key} データ。fitbit_raw.${each.key} の外部起点。"
    system       = "Google Health API"
    platform     = "google-health-api"
    resource     = "googlehealth:activity/${each.key}"

    labels = {
      story = "s4-catalog"
    }
  }

  # generic Entry Type が必須とするアスペクト（type / system の 2 フィールド）。
  aspects {
    aspect_key = local.generic_aspect_key
    aspect {
      data = jsonencode({
        type   = "activity-stream"
        system = "Google Health API"
      })
    }
  }

  # (b) 自前の台帳アスペクト。
  aspects {
    aspect_key = local.governance_aspect_key
    aspect {
      data = jsonencode({
        data_owner       = var.catalog_data_owner
        update_frequency = "DAILY"
        sensitivity      = "HEALTH"
      })
    }
  }

  # aspect_key は文字列組み立てなので aspect_type への暗黙依存が張られない。明示する。
  depends_on = [
    google_dataplex_aspect_type.governance,
    google_project_service.dataplex,
  ]
}
