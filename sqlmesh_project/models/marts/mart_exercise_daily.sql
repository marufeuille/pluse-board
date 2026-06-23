MODEL (
  name fitbit_mart.mart_exercise_daily,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column activity_date
  ),
  cron '@daily',
  grain (activity_date, activity_name),
  audits (
    not_null(columns := (activity_date, activity_name, duration_minutes))
  )
);

SELECT
  DATE(start_time, 'Asia/Tokyo') AS activity_date,
  activity_name,
  SUM(TIMESTAMP_DIFF(end_time, start_time, MINUTE)) AS duration_minutes
FROM fitbit_staging.stg_exercise
WHERE DATE(start_time, 'Asia/Tokyo') BETWEEN @start_ds AND @end_ds
GROUP BY 1, 2
