-- Health API は同じ歩数を Fitbit と Health Connect の両ソースから返す。
-- 時間帯がミリ秒単位でズレているので集約では排除できない。
-- Fitbit アプリ表示と一致させるため、platform = FITBIT のみ採用する。
SELECT
  TIMESTAMP(JSON_VALUE(raw, '$.steps.interval.startTime')) AS start_time,
  TIMESTAMP(JSON_VALUE(raw, '$.steps.interval.endTime'))   AS end_time,
  CAST(JSON_VALUE(raw, '$.steps.count') AS INT64)          AS steps
FROM {{ source('fitbit_raw', 'steps') }}
WHERE JSON_VALUE(raw, '$.dataSource.platform') = 'FITBIT'
  AND JSON_VALUE(raw, '$.steps.interval.startTime') IS NOT NULL
