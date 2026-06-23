#!/usr/bin/env python
"""SQLMesh bot の補助 PR コメントを作成/更新する。

公式 bot のコメントは入口だけなので、レビュー導線を1枚にまとめた sticky コメントを
追加で出す:

  - 変更モデルごとの Checks（SQLMesh の各チェック）への直リンク
  - 変更モデルの PR 環境ビュー / prod の BigQuery コンソール deep-link
  - 変更モデルを中心にした上流→下流のリネージ図（Mermaid）

リネージは SQLMesh のローカル DAG（SQL 解析）だけで作るので BigQuery 接続は不要。
これは補助機能なので、失敗しても常に exit 0 にして本体チェックを巻き込まない。

環境変数:
  GITHUB_TOKEN        コメント投稿 / Checks 取得に使う
  GITHUB_REPOSITORY   "owner/repo"
  PR_NUMBER           プルリクエスト番号
  HEAD_SHA            PR head の SHA（bot が check を貼る対象）
  PR_ENV              PR 仮想環境名（例 pluse_board_30）
  GCP_PROJECT         BigQuery プロジェクト（既定 pluse-board）
  SQLMESH_PROJECT     SQLMesh プロジェクトパス（既定 sqlmesh_project）
  CHANGED_FILES       (任意) 改行/空白区切りの変更ファイル一覧。指定時は API を使わず
                      これを使う（ローカル dry-run 用）
  DRY_RUN             "1" ならコメント投稿せず本文を標準出力に出す
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import urllib.error
import urllib.request

MARKER = "<!-- sqlmesh-pr-extra -->"
API = "https://api.github.com"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _api(method: str, url: str, token: str, body: dict | None = None) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def changed_model_files(repo: str, pr: str, token: str, project: str) -> list[str]:
    """変更された SQLMesh モデルファイル（プロジェクト相対パス）を返す。"""
    prefix = f"{project}/models/"
    raw = _env("CHANGED_FILES")
    if raw:
        files = raw.split()
    else:
        files = []
        page = 1
        while True:
            url = f"{API}/repos/{repo}/pulls/{pr}/files?per_page=100&page={page}"
            chunk = _api("GET", url, token)
            if not chunk:
                break
            files.extend(f["filename"] for f in chunk)
            if len(chunk) < 100:
                break
            page += 1
    return [f for f in files if f.startswith(prefix) and f.endswith(".sql")]


def build_lineage(ctx, changed_fqns: set[str]) -> tuple[set[str], list[tuple[str, str]]]:
    """変更モデルの祖先・子孫を含む部分グラフ（モデルノードのみ）を返す。"""
    graph = ctx.dag.graph  # node -> 直接の上流(依存) 集合
    models = set(ctx.models)  # プロジェクトのモデル fqn のみ（生ソースは除外）

    # 逆隣接（node -> 下流集合）
    children: dict[str, set[str]] = {}
    for node, deps in graph.items():
        for dep in deps:
            children.setdefault(dep, set()).add(node)

    def walk(start: set[str], adj: dict[str, set[str]]) -> set[str]:
        seen: set[str] = set()
        stack = list(start)
        while stack:
            n = stack.pop()
            for nxt in adj.get(n, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen

    ancestors = walk(changed_fqns, graph)
    descendants = walk(changed_fqns, children)
    nodes = (changed_fqns | ancestors | descendants) & models

    edges = []
    for node in nodes:
        for dep in graph.get(node, set()):
            if dep in nodes:
                edges.append((dep, node))
    return nodes, edges


def mermaid(ctx, nodes: set[str], edges: list[tuple[str, str]], changed: set[str]) -> str:
    ids = {fqn: f"n{i}" for i, fqn in enumerate(sorted(nodes))}
    label = {fqn: ctx.models[fqn].view_name for fqn in nodes}
    lines = ["```mermaid", "flowchart LR"]
    for fqn in sorted(nodes):
        lines.append(f'  {ids[fqn]}["{label[fqn]}"]')
    for dep, node in sorted(edges):
        lines.append(f"  {ids[dep]} --> {ids[node]}")
    changed_ids = [ids[f] for f in sorted(changed) if f in ids]
    if changed_ids:
        lines.append(f"  class {','.join(changed_ids)} changed")
        lines.append("  classDef changed fill:#ffd966,stroke:#d6a400,color:#000")
    lines.append("```")
    return "\n".join(lines)


def bq_table_url(project: str, dataset: str, table: str) -> str:
    return (
        f"https://console.cloud.google.com/bigquery?project={project}"
        f"&ws=!1m5!1m4!4m3!1s{project}!2s{dataset}!3s{table}"
    )


def check_links(repo: str, sha: str, token: str) -> list[tuple[str, str]]:
    if not sha:
        return []
    url = f"{API}/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    runs = _api("GET", url, token).get("check_runs", [])
    out = [(r["name"], r["html_url"]) for r in runs if r["name"].startswith("SQLMesh -")]
    return sorted(out)


def upsert_comment(repo: str, pr: str, token: str, body: str) -> None:
    page = 1
    existing_id = None
    while True:
        url = f"{API}/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}"
        chunk = _api("GET", url, token)
        if not chunk:
            break
        for c in chunk:
            if MARKER in c.get("body", ""):
                existing_id = c["id"]
                break
        if existing_id or len(chunk) < 100:
            break
        page += 1
    if existing_id:
        _api("PATCH", f"{API}/repos/{repo}/issues/comments/{existing_id}", token, {"body": body})
    else:
        _api("POST", f"{API}/repos/{repo}/issues/{pr}/comments", token, {"body": body})


def main() -> int:
    repo = _env("GITHUB_REPOSITORY")
    pr = _env("PR_NUMBER")
    token = _env("GITHUB_TOKEN")
    head_sha = _env("HEAD_SHA")
    pr_env = _env("PR_ENV")
    gcp = _env("GCP_PROJECT", "pluse-board")
    project = _env("SQLMESH_PROJECT", "sqlmesh_project")
    dry = _env("DRY_RUN") == "1"

    files = changed_model_files(repo, pr, token, project)
    if not files:
        body = f"{MARKER}\n## 🤖 SQLMesh review links\n\nこの PR にモデル変更はありません。"
        if dry:
            print(body)
        elif token:
            upsert_comment(repo, pr, token, body)
        return 0

    # DAG / モデルはローカル解析のみ（BigQuery 接続不要）
    from sqlmesh import Context

    ctx = Context(paths=project)
    by_path = {os.path.relpath(str(m._path)): fqn for fqn, m in ctx.models.items()}
    changed = {by_path[f] for f in files if f in by_path}

    parts = [MARKER, "## 🤖 SQLMesh review links", ""]

    checks = check_links(repo, head_sha, token) if token else []
    if checks:
        parts.append("### 🔍 Checks")
        parts += [f"- [{name}]({url})" for name, url in checks]
        parts.append("")

    parts.append("### 🗄️ BigQuery（変更モデル）")
    parts.append("| model | PR env | prod |")
    parts.append("|---|---|---|")
    for fqn in sorted(changed):
        m = ctx.models[fqn]
        sch, tbl = m.schema_name, m.view_name
        pr_ds = f"{sch}__{pr_env}" if pr_env else sch
        pr_url = bq_table_url(gcp, pr_ds, tbl)
        prod_url = bq_table_url(gcp, sch, tbl)
        parts.append(f"| `{m.name}` | [開く]({pr_url}) | [開く]({prod_url}) |")
    parts.append("")
    parts.append(
        "> ⚠️ `skip_pr_backfill: true` のため、変更モデルの PR env ビューはデータ 0 行のことがあります"
        "（構造確認用）。"
    )
    parts.append("")

    nodes, edges = build_lineage(ctx, changed)
    if nodes:
        parts.append("### 🌳 Lineage（🔶=変更）")
        parts.append(mermaid(ctx, nodes, edges, changed))

    body = "\n".join(parts)
    if dry:
        print(body)
    elif token:
        upsert_comment(repo, pr, token, body)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # 補助機能なので本体チェックは巻き込まない
        print("sqlmesh_pr_comment failed (non-fatal):", file=sys.stderr)
        traceback.print_exc()
        sys.exit(0)
