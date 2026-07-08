"""SQLMesh を OpenLineage 計装付きで駆動する薄いランナー（Phase 2）。

CLI `sqlmesh --gateway <gw> run|plan` の代替。**config.yaml を一切変更せず**、
sqlmesh-openlineage の console 差し替えでモデル評価ごとに START/COMPLETE/FAIL・
カラム lineage(transformations)・実行統計(rows/bytes/duration) を emit する。

transport は Phase 1 (ingest/lineage.py) と同じく環境変数だけで決まる:

  ローカル Marquez:
    OPENLINEAGE_URL=http://localhost:9000
  Dataplex (Knowledge Catalog):
    OPENLINEAGE_URL=https://datalineage.googleapis.com
    OPENLINEAGE_ENDPOINT=v1/projects/<PROJECT_ID>/locations/<BQ_LOCATION>:processOpenLineageRunEvent
    OPENLINEAGE_API_KEY=<`gcloud auth print-access-token` の出力>
  無効化(既定): OPENLINEAGE_URL を設定しない or OPENLINEAGE_DISABLED=true

lineage は SQLMesh 実行の「副次情報」。未導入・送信失敗・計装セットアップ失敗でも
SQLMesh 本体を絶対に止めない(best-effort)。無効時は素の Context 実行に完全フォールバック。

使い方:
    # daily 相当（prod・ci gateway）
    python run_with_lineage.py run --gateway ci
    python run_with_lineage.py plan --gateway ci
    # ローカル spike（dev 環境・bigquery gateway/DuckDB state・prod を触らない）
    OPENLINEAGE_URL=http://localhost:9000 \\
        python run_with_lineage.py plan --gateway bigquery --environment ol_spike
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent
# BQ 自動リネージ / Phase 1 と同じノードに解決させるため dataset namespace は "bigquery"。
# (project.dataset.table のノードが raw→staging→mart で地続きになる)
_DATASET_NAMESPACE = "bigquery"


def _lineage_enabled() -> bool:
    if os.environ.get("OPENLINEAGE_DISABLED", "false").lower() == "true":
        return False
    return bool(os.environ.get("OPENLINEAGE_URL"))


def _strip_quotes(name: str) -> str:
    """`"proj"."ds"."tbl"` → `proj.ds.tbl`。

    パッケージは親スナップショットを解決できないと `parent_id.name`(クォート付き FQN)
    をそのまま dataset 名にするため、出力ノード(`proj.ds.tbl`)や BQ 自動リネージ/
    Phase 1 のノードと別物になり DAG が分裂する。クォートを剥いてクリーン形式に統一する。
    """
    return name.replace('"', "").replace("`", "")


def _patch_dataset_naming() -> None:
    """入出力 dataset 名を常にクリーンな `proj.ds.tbl` へ正規化する。

    emitter は各メソッド内で `from sqlmesh_openlineage.datasets import ...` する
    (関数ローカル import) ため、モジュール属性を差し替えれば呼び出し時に反映される。
    """
    from sqlmesh_openlineage import datasets as ds

    orig_inputs = ds.snapshot_to_input_datasets
    orig_output = ds.snapshot_to_output_dataset

    # 注意: インストール済み v0.1.0 の snapshot_to_input_datasets は親解決を持たず
    # (snapshots 引数なし) 常にクォート付き名を返す。ここでの正規化が本質的に効く。
    def inputs(snapshot, namespace):
        result = orig_inputs(snapshot, namespace)
        for d in result:
            d.name = _strip_quotes(d.name)
        return result

    def output(snapshot, namespace, facets=None):
        d = orig_output(snapshot, namespace, facets=facets)
        if d is not None:
            d.name = _strip_quotes(d.name)
        return d

    ds.snapshot_to_input_datasets = inputs
    ds.snapshot_to_output_dataset = output


def _install_lineage_console() -> None:
    """OpenLineage 計装 console を global に差し込む。失敗しても例外を投げない。

    パッケージ標準の sqlmesh_openlineage.install(url=...) は使わない。理由 2 点:
      1. dataset を "bigquery" namespace で出したい(install は job と dataset に同一
         namespace を使い、既定だと BQ 自動リネージ/Phase 1 と別ノードになる)。
      2. パッケージ内 OpenLineageClient(url=...) は endpoint が api/v1/lineage 固定で
         Dataplex の OPENLINEAGE_ENDPOINT を無視する。env ベースの OpenLineageClient()
         に差し替えて Dataplex の :processOpenLineageRunEvent を尊重させる。

    Context.__init__ が self.console = get_console() で global console を拾うため、
    Context 生成の「前」に set_console() する必要がある。
    """
    try:
        from openlineage.client import OpenLineageClient
        from sqlmesh.core.console import create_console, set_console
        from sqlmesh_openlineage.console import OpenLineageConsole

        console = OpenLineageConsole(
            wrapped=create_console(),
            url="http://localhost",  # ダミー。直後に env ベース client へ差し替える。
            namespace=_DATASET_NAMESPACE,
        )
        # transport は環境変数だけで決まる(Marquez / Dataplex を env で切替)。Phase 1 と同一。
        console._emitter.client = OpenLineageClient()
        _patch_dataset_naming()
        set_console(console)
        print(f"::notice::OpenLineage 計装を有効化 (namespace={_DATASET_NAMESPACE})")
    except Exception as e:  # 計装セットアップ失敗で SQLMesh を止めない
        print(f"::warning::OpenLineage 計装を無効化 (セットアップ失敗): {e}")


def _context(gateway: str):
    from sqlmesh import Context

    return Context(paths=str(_PROJECT_DIR), gateway=gateway)


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLMesh runner with OpenLineage")
    parser.add_argument("command", choices=["run", "plan"])
    parser.add_argument("--gateway", default="ci")
    # 既定 None = prod（CLI の `sqlmesh run/plan` と同じ）。spike では dev 環境名を渡す。
    parser.add_argument("--environment", default=None)
    args = parser.parse_args()

    if _lineage_enabled():
        _install_lineage_console()  # Context 生成前に console を差し替える

    ctx = _context(args.gateway)
    if args.command == "run":
        ctx.run(args.environment)
    else:
        ctx.plan(args.environment, auto_apply=True, no_prompts=True)


if __name__ == "__main__":
    main()
