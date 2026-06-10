WITH daily_exercise AS (
    SELECT
        activity_date,
        SUM(duration_minutes) as total_duration
    FROM {{ ref('mart_exercise_daily') }}
    GROUP BY 1
),
daily_flags AS (
    SELECT
        activity_date,
        CASE WHEN total_duration > 0 THEN 1 ELSE 0 END AS is_active
    FROM daily_exercise
),
-- Gaps-and-Islands problem: create a group id by subtracting row_number from a dense sequence of dates
streak_groups AS (
    SELECT
        activity_date,
        is_active,
        -- Generate a date sequence so subtracting row number gives the same date for continuous sequences
        DATE_SUB(activity_date, INTERVAL ROW_NUMBER() OVER (PARTITION BY is_active ORDER BY activity_date) DAY) AS streak_grp
    FROM daily_flags
),
streaks AS (
    SELECT
        activity_date,
        is_active,
        streak_grp,
        COUNT(*) OVER (PARTITION BY is_active, streak_grp ORDER BY activity_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as current_streak
    FROM streak_groups
)
SELECT
    activity_date,
    is_active,
    CASE WHEN is_active = 1 THEN current_streak ELSE 0 END AS exercise_streak
FROM streaks
ORDER BY activity_date DESC
