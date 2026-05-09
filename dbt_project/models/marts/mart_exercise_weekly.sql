SELECT
  DATE_TRUNC(activity_date, WEEK(MONDAY)) AS week_start,
  activity_name,
  SUM(duration_minutes)                   AS duration_minutes
FROM {{ ref('mart_exercise_daily') }}
GROUP BY 1, 2
