MODEL (
  name fitbit_staging.stg_exercise,
  kind VIEW
);

WITH deduped AS (
  SELECT raw
  FROM fitbit_raw.exercise
  -- 同一 dataPoint（$.name）の再取り込みは updateTime が最新の行を採用する。
  -- notes 等が後から更新されるケースで新しい方を残すため、順序を決定的にしている。
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY JSON_VALUE(raw, '$.name')
    ORDER BY TIMESTAMP(JSON_VALUE(raw, '$.exercise.updateTime')) DESC
  ) = 1
)
SELECT
  TIMESTAMP(JSON_VALUE(raw, '$.exercise.interval.startTime')) AS start_time,
  TIMESTAMP(JSON_VALUE(raw, '$.exercise.interval.endTime'))   AS end_time,
  JSON_VALUE(raw, '$.exercise.exerciseType')                  AS exercise_type,
  JSON_VALUE(raw, '$.exercise.displayName')                   AS activity_name,
  CAST(REPLACE(JSON_VALUE(raw, '$.exercise.activeDuration'), 's', '') AS FLOAT64)
                                                              AS active_duration_sec,
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.caloriesKcal') AS FLOAT64)
                                                              AS calories_kcal,
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.distanceMillimeters') AS FLOAT64)
                                                              AS distance_mm,
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.distanceMillimeters') AS FLOAT64) / 1e6
                                                              AS distance_km,
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.steps') AS INT64)
                                                              AS steps,
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.activeZoneMinutes') AS INT64)
                                                              AS active_zone_minutes,
  JSON_VALUE(raw, '$.exercise.notes')                         AS notes,
  JSON_VALUE(raw, '$.dataSource.application.packageName')     AS source_app
FROM deduped
