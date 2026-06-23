MODEL (
  name fitbit_mart.mart_strength_daily,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column activity_date
  ),
  cron '@daily',
  grain activity_date,
  audits (
    not_null(columns := (activity_date, session_count, duration_minutes)),
    unique_values(columns := (activity_date))
  )
);

-- 筋トレ（STRENGTH_TRAINING）だけを抜き出した日次サマリ。
-- ACWR の負荷は AZM ベースなので筋トレでは値が立たない。頻度・時間・カロリーで
-- 筋トレの実態を別軸で捉える。active_zone_minutes も持っておき、筋トレで AZM が
-- いかに立たないかを ACWR との対比で見せられるようにする。
SELECT
  DATE(start_time, 'Asia/Tokyo')                    AS activity_date,
  COUNT(*)                                          AS session_count,
  SUM(TIMESTAMP_DIFF(end_time, start_time, MINUTE)) AS duration_minutes,
  SUM(calories_kcal)                                AS calories_kcal,
  SUM(active_zone_minutes)                          AS active_zone_minutes
FROM fitbit_staging.stg_exercise
WHERE exercise_type = 'STRENGTH_TRAINING'
  AND DATE(start_time, 'Asia/Tokyo') BETWEEN @start_ds AND @end_ds
GROUP BY 1
