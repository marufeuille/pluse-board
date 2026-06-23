MODEL (
  name fitbit_staging.stg_steps,
  kind VIEW
);

-- Health API は同じ歩数を Fitbit と Health Connect の両ソースから返す。
-- 時間帯がミリ秒単位でズレているので集約では排除できない。
-- Fitbit アプリ表示と一致させるため、platform = FITBIT のみ採用する。
--
-- さらに ingest が同じ window を複数回投入すると raw に同一レコードが
-- 重複登録されるため、startTime ごとに1件に絞る (stg_active_zone_minutes と同じパターン)。
WITH fitbit_only AS (
  SELECT raw
  FROM fitbit_raw.steps
  WHERE JSON_VALUE(raw, '$.dataSource.platform') = 'FITBIT'
    AND JSON_VALUE(raw, '$.steps.interval.startTime') IS NOT NULL
),
deduped AS (
  SELECT raw
  FROM fitbit_only
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY JSON_VALUE(raw, '$.steps.interval.startTime')
    ORDER BY 1
  ) = 1
)
SELECT
  TIMESTAMP(JSON_VALUE(raw, '$.steps.interval.startTime')) AS start_time,
  TIMESTAMP(JSON_VALUE(raw, '$.steps.interval.endTime'))   AS end_time,
  CAST(JSON_VALUE(raw, '$.steps.count') AS INT64)          AS steps
FROM deduped
