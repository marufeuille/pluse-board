MODEL (
  name fitbit_mart.mart_steps_daily,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column activity_date
  ),
  cron '@daily',
  grain activity_date,
  audits (
    not_null(columns := (activity_date, steps)),
    unique_values(columns := (activity_date)),
    assert_interval_not_empty
  )
);

SELECT
  DATE(start_time, 'Asia/Tokyo') AS activity_date,
  SUM(steps)                     AS steps
FROM fitbit_staging.stg_steps
WHERE DATE(start_time, 'Asia/Tokyo') BETWEEN @start_ds AND @end_ds
GROUP BY 1
