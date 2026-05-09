SELECT
  DATE(start_time, 'Asia/Tokyo') AS activity_date,
  SUM(value)                     AS load
FROM {{ ref('stg_active_zone_minutes') }}
GROUP BY 1
