SELECT
  DATE(interval_civil_start_time) AS activity_date,
  SUM(value)                      AS load
FROM {{ source('fitbit_raw', 'active_zone_minutes') }}
WHERE interval_civil_start_time IS NOT NULL
GROUP BY 1
