MODEL (
  name fitbit_mart.mart_acwr,
  kind FULL,
  cron '@daily',
  grain d,
  audits (
    not_null(columns := (d, load)),
    unique_values(columns := (d))
  )
);

-- 28日トレーリング窓の rolling 平均を全期間に対して計算するため FULL。
-- incremental 化するなら time_column = d + lookback 28 が必要（応用課題）。
--
-- 休養日を 0 埋めしないと rolling 平均が過大評価されるため calendar JOIN は必須。
-- 上限は CURRENT_DATE ではなく ingest 済みの最終日に揃える。steps/exercise が
-- 入っている日は AZM が 0 でも「取得済み」とみなし、末尾の休養日も ACWR に含める。
WITH daily_load AS (
  SELECT
    activity_date AS d,
    load
  FROM fitbit_mart.mart_load_daily
),
available_days AS (
  SELECT d FROM daily_load
  UNION DISTINCT
  SELECT activity_date AS d FROM fitbit_mart.mart_steps_daily
  UNION DISTINCT
  SELECT activity_date AS d FROM fitbit_mart.mart_exercise_daily
),
calendar AS (
  SELECT d
  FROM UNNEST(GENERATE_DATE_ARRAY(
    (SELECT MIN(d) FROM available_days),
    (SELECT MAX(d) FROM available_days)
  )) AS d
),
filled AS (
  SELECT
    c.d,
    COALESCE(dl.load, 0) AS load
  FROM calendar c
  LEFT JOIN daily_load dl USING (d)
)
SELECT
  d,
  load,
  AVG(load) OVER (ORDER BY d ROWS BETWEEN 6  PRECEDING AND CURRENT ROW) AS acute_7d,
  AVG(load) OVER (ORDER BY d ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS chronic_28d,
  -- chronic 期間（28日）が揃ってない初期データは ACWR を計算しない
  CASE
    WHEN COUNT(*) OVER (ORDER BY d ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) < 28
    THEN NULL
    ELSE SAFE_DIVIDE(
      AVG(load) OVER (ORDER BY d ROWS BETWEEN 6  PRECEDING AND CURRENT ROW),
      AVG(load) OVER (ORDER BY d ROWS BETWEEN 27 PRECEDING AND CURRENT ROW)
    )
  END AS acwr,
  -- SQLMesh CI/CD bot 動作確認用のダミー列。マージしない（このPRは検証専用）。
  TRUE AS _bot_smoke_test
FROM filled
