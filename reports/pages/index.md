# Pluse Board

```sql summary
SELECT
  (SELECT SUM(duration_minutes)
   FROM bq.mart_exercise_daily
   WHERE activity_date >= CURRENT_DATE - INTERVAL 7 DAY)  AS exercise_min_7d,
  (SELECT SUM(steps)
   FROM bq.mart_steps_daily
   WHERE activity_date >= CURRENT_DATE - INTERVAL 7 DAY)  AS steps_7d,
  (SELECT ROUND(acwr, 2)
   FROM bq.mart_acwr
   ORDER BY d DESC LIMIT 1)                               AS latest_acwr
```

<BigValue
  data={summary}
  value=exercise_min_7d
  title="直近7日の運動時間（分）"
  fmt="#,##0"
/>

<BigValue
  data={summary}
  value=steps_7d
  title="直近7日の歩数"
  fmt="#,##0"
/>

<BigValue
  data={summary}
  value=latest_acwr
  title="最新 ACWR"
  fmt="0.00"
/>

## 直近30日の運動時間

```sql recent_exercise
SELECT activity_date, activity_name, duration_minutes
FROM bq.mart_exercise_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 30 DAY
ORDER BY activity_date
```

<BarChart
  data={recent_exercise}
  x=activity_date
  y=duration_minutes
  series=activity_name
  type=stacked
  title="直近30日の運動時間"
  yAxisTitle="分"
/>

## 直近30日の歩数

```sql recent_steps
SELECT activity_date, steps
FROM bq.mart_steps_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 30 DAY
ORDER BY activity_date
```

<LineChart
  data={recent_steps}
  x=activity_date
  y=steps
  title="直近30日の歩数"
  yAxisTitle="歩"
/>
