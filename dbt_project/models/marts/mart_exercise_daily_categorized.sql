-- WALKING は AZM/active 分 >= 0.5 をパワーウォークとして区別する。
-- STRENGTH_TRAINING は筋トレ。それ以外（Fitbit「Other」を含む）は「その他運動」に集約。
WITH classified AS (
  SELECT
    DATE(start_time, 'Asia/Tokyo') AS activity_date,
    CASE
      WHEN exercise_type = 'STRENGTH_TRAINING' THEN '筋トレ'
      WHEN exercise_type = 'WALKING'
        AND SAFE_DIVIDE(active_zone_minutes, GREATEST(active_duration_sec / 60.0, 1)) >= 0.5
        THEN 'パワーウォーク'
      WHEN exercise_type = 'WALKING' THEN 'ウォーキング'
      ELSE 'その他運動'
    END AS category,
    TIMESTAMP_DIFF(end_time, start_time, MINUTE) AS duration_minutes
  FROM {{ ref('stg_exercise') }}
)
SELECT
  activity_date,
  category,
  SUM(duration_minutes) AS duration_minutes
FROM classified
GROUP BY 1, 2
