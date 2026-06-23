MODEL (
  name fitbit_mart.mart_strength_streak,
  kind FULL,
  cron '@daily',
  audits (
    not_null(columns := (current_streak_weeks, best_streak_weeks))
  )
);

-- 週3回以上（meets_target）を満たした週の連続数（ストリーク）を gaps-and-islands で算出。
-- 1行だけ返し、Evidence の BigValue で「現在のストリーク / ベストストリーク」を見せる。
--
-- 注意: 最新週は進行中で週3回未達のことがあり、その場合 current_streak は週途中で0表示になる。
-- 気になれば「進行中の週を除外」または「直近の完了週基準」に切り替える（応用課題）。
WITH flagged AS (
  SELECT
    week_start,
    meets_target,
    ROW_NUMBER() OVER (ORDER BY week_start)
      - ROW_NUMBER() OVER (PARTITION BY meets_target ORDER BY week_start) AS grp
  FROM fitbit_mart.mart_strength_weekly
),
runs AS (
  SELECT
    grp,
    COUNT(*)        AS run_len,
    MAX(week_start) AS run_end
  FROM flagged
  WHERE meets_target
  GROUP BY grp
)
SELECT
  -- 最新週で終わる達成ランの長さ（最新週が未達なら該当ランが無く 0）
  COALESCE((
    SELECT run_len
    FROM runs
    WHERE run_end = (SELECT MAX(week_start) FROM fitbit_mart.mart_strength_weekly)
  ), 0) AS current_streak_weeks,
  COALESCE((SELECT MAX(run_len) FROM runs), 0) AS best_streak_weeks
