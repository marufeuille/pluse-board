# 運動の推移

```sql daily_exercise
SELECT
  activity_date,
  activity_name,
  duration_minutes
FROM bq.mart_exercise_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 90 DAY
ORDER BY activity_date
```

<BarChart
  data={daily_exercise}
  x=activity_date
  y=duration_minutes
  series=activity_name
  type=stacked
  title="日次運動時間（種別ごと）"
  yAxisTitle="分"
/>

## 週次比較

```sql weekly_exercise
SELECT
  DATE_TRUNC('week', activity_date) AS week_start,
  activity_name,
  SUM(duration_minutes)                   AS duration_minutes
FROM bq.mart_exercise_daily
GROUP BY 1, 2
ORDER BY 1
```

<BarChart
  data={weekly_exercise}
  x=week_start
  y=duration_minutes
  series=activity_name
  type=stacked
  title="週次運動時間（種別ごと）"
  yAxisTitle="分"
/>

## 月次比較

```sql monthly_exercise
SELECT
  DATE_TRUNC('month', activity_date) AS month_start,
  activity_name,
  SUM(duration_minutes)            AS duration_minutes
FROM bq.mart_exercise_daily
GROUP BY 1, 2
ORDER BY 1
```

<BarChart
  data={monthly_exercise}
  x=month_start
  y=duration_minutes
  series=activity_name
  type=stacked
  title="月次運動時間（種別ごと）"
  yAxisTitle="分"
/>
