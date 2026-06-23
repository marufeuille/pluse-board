MODEL (
  name fitbit_staging.stg_active_zone_minutes,
  kind VIEW
);

WITH deduped AS (
  SELECT raw
  FROM fitbit_raw.active_zone_minutes
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY
      JSON_VALUE(raw, '$.activeZoneMinutes.interval.startTime'),
      JSON_VALUE(raw, '$.activeZoneMinutes.heartRateZone')
    ORDER BY 1
  ) = 1
)
SELECT
  TIMESTAMP(JSON_VALUE(raw, '$.activeZoneMinutes.interval.startTime')) AS start_time,
  TIMESTAMP(JSON_VALUE(raw, '$.activeZoneMinutes.interval.endTime'))   AS end_time,
  JSON_VALUE(raw, '$.activeZoneMinutes.heartRateZone')                 AS heart_rate_zone,
  CAST(JSON_VALUE(raw, '$.activeZoneMinutes.activeZoneMinutes') AS INT64)
                                                                       AS value
FROM deduped
