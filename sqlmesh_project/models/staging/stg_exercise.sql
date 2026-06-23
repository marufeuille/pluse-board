MODEL (
  name fitbit_staging.stg_exercise,
  kind VIEW
);

WITH deduped AS (
  SELECT raw
  FROM fitbit_raw.exercise
  QUALIFY ROW_NUMBER() OVER (PARTITION BY JSON_VALUE(raw, '$.name') ORDER BY 1) = 1
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
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.steps') AS INT64)
                                                              AS steps,
  CAST(JSON_VALUE(raw, '$.exercise.metricsSummary.activeZoneMinutes') AS INT64)
                                                              AS active_zone_minutes
FROM deduped
