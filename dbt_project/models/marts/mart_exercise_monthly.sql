SELECT
  DATE_TRUNC(activity_date, MONTH) AS month_start,
  activity_name,
  SUM(duration_minutes)            AS duration_minutes
FROM {{ ref('mart_exercise_daily') }}
GROUP BY 1, 2
