#!/usr/bin/env bash
#
# Dataplex データ品質スキャンを起動し、完了を待って合否を判定する（S3）。
#
# lineage（ingest/lineage.py）と同じ best-effort 原則で書いてある。スキャン起動・
# ポーリング・結果パースのどこで失敗しても ::warning:: を出して status=error で exit 0 する。
# Daily Build は絶対に止めない。「品質を測れなかった」ことと「品質が悪い」ことは別物なので、
# status=error は通知経路（notify_dq）にも乗せない。
#
# gcloud CLI には依存せず、WIF で得た短命 access_token を Bearer に使う。
#
# 必要な環境変数:
#   PROJECT_ID   GCP プロジェクト ID
#   BQ_LOCATION  DataScan のリージョン（DataScan はリージョナル）
#   DATASCAN_ID  起動する DataScan の ID
#   ACCESS_TOKEN WIF で発行した短命アクセストークン
#
# 出力（GITHUB_OUTPUT / GITHUB_STEP_SUMMARY。ローカル実行時は stdout）:
#   status       pass | fail | error
#   score        品質スコア（0-100。取得できなければ空）
#   job_name     DataScan ジョブのリソース名
#   failed_rules 失敗したルールの一覧（複数行）

set -uo pipefail   # -e は付けない。best-effort でどのコマンドが失敗しても最後まで進む。

readonly POLL_INTERVAL_SEC=10
readonly POLL_TIMEOUT_SEC=600

: "${PROJECT_ID:?PROJECT_ID is required}"
: "${BQ_LOCATION:?BQ_LOCATION is required}"
: "${DATASCAN_ID:?DATASCAN_ID is required}"
: "${ACCESS_TOKEN:?ACCESS_TOKEN is required}"

readonly API_ROOT="https://dataplex.googleapis.com/v1"
readonly SCAN="projects/${PROJECT_ID}/locations/${BQ_LOCATION}/dataScans/${DATASCAN_ID}"

status="error"
score=""
job_name=""
failed_rules=""

# GITHUB_OUTPUT / GITHUB_STEP_SUMMARY はローカル実行では未設定。/dev/stdout に落とす。
emit_outputs() {
  local out="${GITHUB_OUTPUT:-/dev/stdout}"
  {
    echo "status=${status}"
    echo "score=${score}"
    echo "job_name=${job_name}"
    echo "failed_rules<<DQ_RULES_EOF"
    echo "${failed_rules}"
    echo "DQ_RULES_EOF"
  } >> "$out"

  local summary="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
  {
    echo "## Dataplex データ品質スキャン (${DATASCAN_ID})"
    echo
    echo "- 判定: \`${status}\`"
    [ -n "$score" ] && echo "- スコア: \`${score}\`"
    [ -n "$job_name" ] && echo "- ジョブ: \`${job_name}\`"
    if [ -n "$failed_rules" ]; then
      echo
      echo "### 失敗ルール"
      echo
      echo "$failed_rules"
    fi
  } >> "$summary"
}

# 失敗しても exit 0。呼び出し側（daily.yml）は status で分岐する。
fail_soft() {
  echo "::warning::Dataplex DQ スキャン: $1"
  status="error"
  emit_outputs
  exit 0
}

api_get() {
  curl --fail --silent --show-error --max-time 30 \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    "$1"
}

# --- スキャン起動 ---------------------------------------------------------
run_response="$(
  curl --fail --silent --show-error --max-time 30 \
    -X POST \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{}' \
    "${API_ROOT}/${SCAN}:run"
)" || fail_soft "起動に失敗した（${SCAN}:run）。権限 roles/dataplex.dataScanEditor を確認する。"

job_name="$(jq -r '.job.name // empty' <<< "$run_response")"
[ -n "$job_name" ] || fail_soft "起動レスポンスに job.name が無い: ${run_response}"

echo "DataScan ジョブを起動した: ${job_name}"

# --- 完了までポーリング ---------------------------------------------------
job_state=""
deadline=$(( SECONDS + POLL_TIMEOUT_SEC ))
while [ "$SECONDS" -lt "$deadline" ]; do
  job_json="$(api_get "${API_ROOT}/${job_name}?view=FULL")" ||
    fail_soft "ジョブの取得に失敗した（${job_name}）。権限 roles/dataplex.dataScanDataViewer を確認する。"

  job_state="$(jq -r '.state // empty' <<< "$job_json")"
  case "$job_state" in
    SUCCEEDED | FAILED | CANCELLED) break ;;
    *) sleep "$POLL_INTERVAL_SEC" ;;
  esac
done

case "$job_state" in
  SUCCEEDED) ;;
  FAILED | CANCELLED) fail_soft "ジョブが ${job_state} で終了した（品質の合否は不明）。" ;;
  *) fail_soft "${POLL_TIMEOUT_SEC}s 待ってもジョブが完了しなかった（最終 state=${job_state:-unknown}）。" ;;
esac

# --- 結果パース -----------------------------------------------------------
# 【重要】Dataplex の JSON は proto3 の既定値省略に従うため、FAIL 時は
# `passed` フィールドが false ではなく "存在しない" 状態で返る（rules[].passed も同じ）。
# したがって
#   - 「passed が無い＝結果を読めていない」と読むと FAIL を握り潰す
#   - `select(.passed == false)` では失敗ルールを 1 件も拾えない
# 結果を読めたかどうかは dataQualityResult ブロックの有無で判定し、passed は false に倒す。
# dataScanDataViewer が無いとこのブロックごと返らないので、その場合だけ error になる。
jq -e 'has("dataQualityResult")' <<< "$job_json" > /dev/null ||
  fail_soft "結果に dataQualityResult が無い。roles/dataplex.dataScanDataViewer が付いているか確認する。"

passed="$(jq -r '.dataQualityResult.passed // false' <<< "$job_json")"
score="$(jq -r '.dataQualityResult.score // empty' <<< "$job_json")"

# 失敗ルールを「dimension / column / passRatio」の Markdown 箇条書きにする。
# `!= true` なのは上記のとおり false が省略されるため（null も拾う）。
# column はテーブルレベルのルール（FRESHNESS 等）では存在しないので "(table)" に落とす。
failed_rules="$(
  jq -r '
    .dataQualityResult.rules // []
    | map(select(.passed != true))
    | .[]
    | "- **\(.rule.dimension // "?")** `\(.rule.column // "(table)")` — passRatio \(.passRatio // 0) (\(.passedCount // 0)/\(.evaluatedCount // 0)) \(.rule.description // "")"
  ' <<< "$job_json"
)"

if [ "$passed" = "true" ]; then
  status="pass"
  echo "品質スキャン PASS (score=${score})"
else
  status="fail"
  echo "::warning::品質スキャン FAIL (score=${score})"
  echo "$failed_rules"
fi

emit_outputs
