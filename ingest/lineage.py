"""OpenLineage イベントを emit する薄いヘルパ。

送信先(transport)は環境変数だけで決まる。このモジュールはバックエンド非依存:

  ローカル Marquez:
    OPENLINEAGE_URL=http://localhost:9000

  Dataplex (Knowledge Catalog):
    OPENLINEAGE_URL=https://datalineage.googleapis.com
    OPENLINEAGE_ENDPOINT=v1/projects/<PROJECT_ID>/locations/<BQ_LOCATION>:processOpenLineageRunEvent
    OPENLINEAGE_API_KEY=<`gcloud auth print-access-token` の出力>

  無効化(既定): OPENLINEAGE_URL を設定しない or OPENLINEAGE_DISABLED=true

lineage は取り込みの「副次情報」なので、送信失敗や openlineage 未導入で
本番の ingest を絶対に止めない(best-effort。失敗は ::warning:: で可視化のみ)。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

# OpenLineage 命名規約:
#   BigQuery テーブル → namespace="bigquery" / name="project.dataset.table"
#                       (BQ 自動リネージと同じノードに解決され raw→staging→mart と地続きに)
#   外部ソース         → namespace="custom"   / name="任意の参照文字列" (FQN: custom:...)
_JOB_NAMESPACE = "pluse-board"
_PRODUCER = "https://github.com/marufeuille/pluse-board"


def _enabled() -> bool:
    if os.environ.get("OPENLINEAGE_DISABLED", "false").lower() == "true":
        return False
    return bool(os.environ.get("OPENLINEAGE_URL"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def track_ingest(
    data_type: str, project: str, dataset: str, table: str
) -> Iterator[None]:
    """ingest の 1 データタイプ分を START/COMPLETE/FAIL で包む。無効時は no-op。"""
    if not _enabled():
        yield
        return

    try:
        from openlineage.client import OpenLineageClient
        from openlineage.client.event_v2 import (
            InputDataset,
            Job,
            OutputDataset,
            Run,
            RunEvent,
            RunState,
        )
        from openlineage.client.facet_v2 import schema_dataset
        from openlineage.client.uuid import generate_new_uuid
    except Exception as e:  # openlineage 未導入など。ingest は続行する。
        print(f"::warning::OpenLineage 無効化 (import 失敗): {e}")
        yield
        return

    client = OpenLineageClient()  # transport は環境変数から
    run = Run(runId=str(generate_new_uuid()))
    job = Job(namespace=_JOB_NAMESPACE, name=f"ingest.{data_type}")
    inputs = [
        InputDataset(namespace="custom", name=f"googlehealth:activity/{data_type}")
    ]
    outputs = [
        OutputDataset(
            namespace="bigquery",
            name=f"{project}.{dataset}.{table}",
            facets={
                "schema": schema_dataset.SchemaDatasetFacet(
                    fields=[
                        schema_dataset.SchemaDatasetFacetFields(name="name", type="STRING"),
                        schema_dataset.SchemaDatasetFacetFields(name="raw", type="STRING"),
                    ]
                )
            },
        )
    ]

    def _emit(state: "RunState") -> None:
        try:
            client.emit(
                RunEvent(
                    eventType=state,
                    eventTime=_now(),
                    run=run,
                    job=job,
                    producer=_PRODUCER,
                    inputs=inputs,
                    outputs=outputs,
                )
            )
        except Exception as e:  # lineage 送信失敗で ingest を止めない
            print(f"::warning::OpenLineage emit 失敗 ({state}): {e}")

    _emit(RunState.START)
    try:
        yield
    except Exception:
        _emit(RunState.FAIL)
        raise
    else:
        _emit(RunState.COMPLETE)


if __name__ == "__main__":
    # スモークテスト: 実データや BQ に触れず emit だけ確認する。
    #   Marquez:  OPENLINEAGE_URL=http://localhost:9000 \
    #             uv run --group lineage python ingest/lineage.py
    os.environ.setdefault("OPENLINEAGE_URL", "http://localhost:9000")
    with track_ingest("exercise", "pluse-board", "fitbit_raw", "exercise"):
        print("emitting demo START/COMPLETE ...")
    print("done")
