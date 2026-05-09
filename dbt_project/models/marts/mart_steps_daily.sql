SELECT
  DATE(interval_civil_start_time) AS activity_date,
  SUM(steps)                      AS steps
FROM {{ source('fitbit_raw', 'steps') }}
WHERE interval_civil_start_time IS NOT NULL
GROUP BY 1
