MODEL (
  name fitbit_mart.mart_load_daily,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column activity_date
  ),
  cron '@daily',
  grain activity_date,
  audits (
    not_null(columns := (activity_date, load)),
    unique_values(columns := (activity_date))
  )
);

SELECT
  DATE(start_time, 'Asia/Tokyo') AS activity_date,
  SUM(value)                     AS load
FROM fitbit_staging.stg_active_zone_minutes
WHERE DATE(start_time, 'Asia/Tokyo') BETWEEN @start_ds AND @end_ds
GROUP BY 1
