#!/usr/bin/env bash
#
# ビジネスグロッサリの用語を BigQuery カラムに紐付ける（S5）。
#
# Dataplex では用語↔カラムの紐付けは「definition タイプの EntryLink」で表す。
# EntryLink は Terraform にも gcloud にもリソースが無く REST API しか経路が無い。
# しかも実体は Dataplex が自動生成する system entry group `@bigquery` の配下に
# 作られる（= TF 管理外）。よって terraform ではなくこのスクリプトで作る。
# Glossary / Category / Term 側は terraform/glossary.tf が管理する。
#
# 冪等。既に存在するリンクは GET でスキップする（同じ ID への再 POST は 409）。
#
# 使い方:
#   scripts/dataplex_glossary_links.sh            # 不足しているリンクを作る
#   scripts/dataplex_glossary_links.sh --verify   # 用語側から逆引きして確認する
#   scripts/dataplex_glossary_links.sh --delete   # 作ったリンクを全部消す
#
# 環境変数（すべて既定値あり）:
#   PROJECT_ID  GCP プロジェクト ID
#   REGION      Glossary と BigQuery エントリのロケーション
#   GLOSSARY_ID terraform/glossary.tf の glossary_id

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-pluse-board}"
REGION="${REGION:-asia-northeast1}"
GLOSSARY_ID="${GLOSSARY_ID:-health-metrics}"

readonly API_ROOT="https://dataplex.googleapis.com/v1"
readonly LINK_TYPE="projects/dataplex-types/locations/global/entryLinkTypes/definition"

# 用語とカラムの対応表: <dataset>:<table>:<column>:<term_id>
# 定義の原典は reports/pages/about.md、用語の実体は terraform/glossary.tf。
readonly LINKS=(
  "fitbit_mart:mart_acwr:acwr:acwr"
  "fitbit_mart:mart_load_daily:load:training-load"
  "fitbit_mart:mart_strength_weekly:meets_target:strength-target"
  "fitbit_staging:stg_active_zone_minutes:value:active-zone-minutes"
)

# EntryLink の参照はプロジェクト「番号」表記（S4 の Entry 系と同じ。ID を渡すと参照が解決されない）。
project_number="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
token="$(gcloud auth print-access-token)"

readonly ENTRY_GROUP="projects/${project_number}/locations/${REGION}/entryGroups/@bigquery"
readonly DATAPLEX_GROUP="projects/${project_number}/locations/${REGION}/entryGroups/@dataplex"

# BigQuery エントリの ID は `DATASET.TABLE` ではなくフルリソースパス（S4 で確認済み）。
bq_entry() {
  echo "${ENTRY_GROUP}/entries/bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/$1/tables/$2"
}

# 用語エントリは @dataplex エントリグループの中に、用語のリソース名をそのまま entry_id として持つ。
term_entry() {
  echo "${DATAPLEX_GROUP}/entries/projects/${project_number}/locations/${REGION}/glossaries/${GLOSSARY_ID}/terms/$1"
}

# EntryLink の ID は [a-z0-9-]。テーブル名とカラム名から決定的に組み立てて冪等性の鍵にする。
link_id() {
  echo "def-$1-$2" | tr '_' '-'
}

api() {
  local method="$1" url="$2"
  shift 2
  curl --silent --show-error --max-time 30 \
    -X "$method" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    "$@" "$url"
}

http_code() {
  local method="$1" url="$2"
  shift 2
  curl --silent --output /dev/null --write-out '%{http_code}' --max-time 30 \
    -X "$method" \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    "$@" "$url"
}

create_links() {
  for spec in "${LINKS[@]}"; do
    IFS=: read -r dataset table column term <<< "$spec"
    local id url
    id="$(link_id "$table" "$column")"
    url="${API_ROOT}/${ENTRY_GROUP}/entryLinks/${id}"

    if [ "$(http_code GET "$url")" = "200" ]; then
      echo "skip   ${dataset}.${table}.${column} -> ${term} (${id} は作成済み)"
      continue
    fi

    # path が実スキーマに無いカラムだと API は 404 を返す（サイレントに作られない）。
    local body
    body="$(jq -n \
      --arg type "$LINK_TYPE" \
      --arg src "$(bq_entry "$dataset" "$table")" \
      --arg path "Schema.${column}" \
      --arg tgt "$(term_entry "$term")" \
      '{entry_link_type: $type,
        entry_references: [
          {name: $src, path: $path, type: "SOURCE"},
          {name: $tgt, type: "TARGET"}
        ]}')"

    api POST "${API_ROOT}/${ENTRY_GROUP}/entryLinks?entry_link_id=${id}" -d "$body" \
      | jq -e '.name' > /dev/null
    echo "create ${dataset}.${table}.${column} -> ${term} (${id})"
  done
}

# 用語側から逆引きする（リンクがカタログ検索・用語ページに載っているかの確認）。
# 紐付いたカラムはレスポンスの entryReferences[].path に入る。
#
# 注意: 公式ドキュメントの curl 例は `-X POST` だが lookupEntryLinks は GET。
# POST で叩くとルーティングされず HTML の 404 が返る（JSON ですらない）。
verify_links() {
  for spec in "${LINKS[@]}"; do
    IFS=: read -r _ _ _ term <<< "$spec"
    echo "--- term: ${term}"
    api GET "${API_ROOT}/projects/${PROJECT_ID}/locations/${REGION}:lookupEntryLinks?entry=$(term_entry "$term")&entry_link_types=${LINK_TYPE}&entry_mode=TARGET" \
      | jq -r '.entryLinks[]?.entryReferences[]
               | select(.type == "SOURCE")
               | "    \(.name | split("/") | "\(.[-3]).\(.[-1])") \(.path)"'
  done
}

delete_links() {
  for spec in "${LINKS[@]}"; do
    IFS=: read -r _ table column _ <<< "$spec"
    local id code
    id="$(link_id "$table" "$column")"
    code="$(http_code DELETE "${API_ROOT}/${ENTRY_GROUP}/entryLinks/${id}")"
    echo "delete ${id} (HTTP ${code})"
  done
}

case "${1:-}" in
  "")        create_links ;;
  --verify)  verify_links ;;
  --delete)  delete_links ;;
  *)         echo "usage: $0 [--verify|--delete]" >&2; exit 2 ;;
esac
