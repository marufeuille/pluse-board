SELECT
  DATE(interval_civil_start_time)  AS activity_date,
  activity_name,
  SUM(
    TIMESTAMP_DIFF(
      CAST(interval_civil_end_time   AS TIMESTAMP),
      CAST(interval_civil_start_time AS TIMESTAMP),
      MINUTE
    )
  )                                AS duration_minutes
FROM {{ source('fitbit_raw', 'exercise') }}
WHERE interval_civil_start_time IS NOT NULL
GROUP BY 1, 2
