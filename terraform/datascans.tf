locals {
  # DataScan の data source は BigQuery の相対リソース名で指定する。
  # SQLMesh prod マートは VIEW だが DataScan は VIEW でも動作する（本リポで実証済み）。
  target_resource = "//bigquery.googleapis.com/projects/${var.project_id}/datasets/${var.mart_dataset}/tables/${var.scan_target_table}"
}

# =====================================================================
# Story 1: データプロファイルスキャン
#   ルールを書かずに列統計（null率/distinct/min/max/分位/最頻値）を自動取得。
#   S2 の品質ルールしきい値の「根拠＝現状把握」を得るためのスキャン。
#
#   注意（学び）: provider google v6.50 の data_profile_spec には
#   catalog_publishing 相当のフィールドが無い（data_quality_spec のみ対応）。
#   プロファイル結果を BigQuery「データプロファイル」タブに公開したい場合は
#   gcloud の `--enable-catalog-publishing` を使う（= Terraform カバレッジのギャップ）。
# =====================================================================
resource "google_dataplex_datascan" "mart_steps_profile" {
  project      = var.project_id
  location     = var.region
  data_scan_id = "mart-steps-daily-profile"
  display_name = "mart_steps_daily データプロファイル (S1)"
  description  = "S1: mart_steps_daily の列統計を自動プロファイル。品質ルールの根拠。"

  labels = {
    purpose = "governance-learning"
    story   = "s1-profile"
  }

  data {
    resource = local.target_resource
  }

  # 学習用途は手動トリガーで十分（無料枠なしのため課金を垂れ流さない）。
  execution_spec {
    trigger {
      on_demand {}
    }
  }

  data_profile_spec {}

  depends_on = [google_project_service.dataplex]
}

# =====================================================================
# Story 2: データ品質スキャン（AutoDQ）
#   ドメイン知識ベースのルールを宣言し PASS/FAIL を継続監視する「ガバナンス層」。
#   同じ not_null/unique を SQLMesh audit（パイプライン内ゲート）にも置いており、
#   「ゲート」と「監視」の役割分担を体感するのが狙い（docs 参照）。
# =====================================================================
resource "google_dataplex_datascan" "mart_steps_quality" {
  project      = var.project_id
  location     = var.region
  data_scan_id = "mart-steps-daily-quality"
  display_name = "mart_steps_daily データ品質 (S2)"
  description  = "S2: mart_steps_daily のドメイン品質ルール。SQLMesh audit と役割分担を対比。"

  labels = {
    purpose = "governance-learning"
    story   = "s2-quality"
  }

  data {
    resource = local.target_resource
  }

  # トリガーは on_demand。デイリー監視は Dataplex 側のスケジュールではなく
  # daily.yml（Daily Build）の SQLMesh run 直後に CI から起動する（S3）。
  # 新鮮なデータの直後に同期的に合否を判定でき、FAIL を beads/Slack に流せる。
  execution_spec {
    trigger {
      on_demand {}
    }
  }

  data_quality_spec {
    # 結果を Dataplex Catalog / BigQuery「データ品質」タブに公開する。
    catalog_publishing_enabled = var.enable_catalog_publishing

    # activity_date は欠損しない（SQLMesh not_null audit と同じ意図を監視層でも）
    rules {
      column      = "activity_date"
      dimension   = "COMPLETENESS"
      description = "日付は必ず存在する"
      non_null_expectation {}
    }

    # activity_date は日毎に一意（SQLMesh unique_values audit と同じ意図）
    rules {
      column      = "activity_date"
      dimension   = "UNIQUENESS"
      description = "1 日 1 行"
      uniqueness_expectation {}
    }

    # steps はドメイン上限内（プロファイル実測 max=19253 → 上限 100000 は安全側）
    rules {
      column      = "steps"
      dimension   = "VALIDITY"
      description = "歩数は 0〜100000 の現実的範囲"
      range_expectation {
        min_value = "0"
        max_value = "100000"
      }
    }

    # 鮮度: 最新 activity_date が 2 日以内。日次取り込みの遅延を監視層でも検知。
    rules {
      dimension   = "FRESHNESS"
      description = "最新データが 2 日以内に存在する"
      table_condition_expectation {
        sql_expression = "MAX(activity_date) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)"
      }
    }
  }

  depends_on = [google_project_service.dataplex]
}
