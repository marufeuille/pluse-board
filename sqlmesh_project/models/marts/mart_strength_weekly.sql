MODEL (
  name fitbit_mart.mart_strength_weekly,
  kind FULL,
  cron '@daily',
  grain week_start,
  audits (
    not_null(columns := (week_start, sessions)),
    unique_values(columns := (week_start))
  )
);

-- 週/月集計は期間境界の再集計が必要なため FULL（毎回全件再構築）。
--
-- streak 判定のため、筋トレ0回の欠週も calendar で0埋めする（埋めないと
-- 「サボった週」が消えて連続達成が途切れなくなる。mart_acwr の calendar JOIN と同じ思想）。
-- 週レンジは「最初の筋トレ週」〜「ingest 済み最新活動日が属する週」。直近に筋トレが
-- 無い週も streak を正しく切れるよう、上限は mart_exercise_daily の最終日に揃える。
-- 週はじまりは about.md の定義どおり日曜（WEEK(SUNDAY)）。
WITH weekly AS (
  SELECT
    DATE_TRUNC(activity_date, WEEK(SUNDAY)) AS week_start,
    SUM(session_count)                      AS sessions,
    COUNT(DISTINCT activity_date)           AS active_days,
    SUM(duration_minutes)                   AS duration_minutes,
    SUM(calories_kcal)                      AS calories_kcal
  FROM fitbit_mart.mart_strength_daily
  GROUP BY 1
),
bounds AS (
  SELECT
    (SELECT MIN(week_start) FROM weekly) AS min_w,
    DATE_TRUNC(
      (SELECT MAX(activity_date) FROM fitbit_mart.mart_exercise_daily),
      WEEK(SUNDAY)
    ) AS max_w
),
calendar AS (
  SELECT w AS week_start
  FROM bounds,
    UNNEST(GENERATE_DATE_ARRAY(min_w, max_w, INTERVAL 7 DAY)) AS w
)
SELECT
  c.week_start,
  COALESCE(wk.sessions, 0)         AS sessions,
  COALESCE(wk.active_days, 0)      AS active_days,
  COALESCE(wk.duration_minutes, 0) AS duration_minutes,
  COALESCE(wk.calories_kcal, 0)    AS calories_kcal,
  COALESCE(wk.sessions, 0) >= 3    AS meets_target
FROM calendar c
LEFT JOIN weekly wk USING (week_start)
