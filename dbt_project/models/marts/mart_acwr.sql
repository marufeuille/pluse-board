-- 休養日を 0 埋めしないと rolling 平均が過大評価されるため calendar JOIN は必須
WITH daily_load AS (
  SELECT
    activity_date AS d,
    load
  FROM {{ ref('mart_load_daily') }}
),
calendar AS (
  SELECT d
  FROM UNNEST(GENERATE_DATE_ARRAY(
    (SELECT MIN(d) FROM daily_load),
    CURRENT_DATE()
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
  SAFE_DIVIDE(
    AVG(load) OVER (ORDER BY d ROWS BETWEEN 6  PRECEDING AND CURRENT ROW),
    AVG(load) OVER (ORDER BY d ROWS BETWEEN 27 PRECEDING AND CURRENT ROW)
  ) AS acwr
FROM filled
