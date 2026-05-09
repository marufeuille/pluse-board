SELECT
  DATE(start_time, 'Asia/Tokyo') AS activity_date,
  activity_name,
  SUM(TIMESTAMP_DIFF(end_time, start_time, MINUTE)) AS duration_minutes
FROM {{ ref('stg_exercise') }}
GROUP BY 1, 2
