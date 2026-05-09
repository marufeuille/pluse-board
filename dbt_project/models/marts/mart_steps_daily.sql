SELECT
  DATE(start_time, 'Asia/Tokyo') AS activity_date,
  SUM(steps)                     AS steps
FROM {{ ref('stg_steps') }}
GROUP BY 1
