MODEL (
  name fitbit_mart.mart_exercise_weekly,
  kind FULL,
  cron '@daily',
  grain (week_start, activity_name),
  audits (
    not_null(columns := (week_start, activity_name, duration_minutes))
  )
);

-- 週/月集計は期間境界の再集計が必要なため、現状は FULL（毎回全件再構築）。
-- incremental 化（time_column = week_start + lookback）は応用課題。
SELECT
  DATE_TRUNC(activity_date, WEEK(MONDAY)) AS week_start,
  activity_name,
  SUM(duration_minutes)                   AS duration_minutes
FROM fitbit_mart.mart_exercise_daily
GROUP BY 1, 2
