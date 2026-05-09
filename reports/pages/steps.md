# 歩数の推移

```sql steps_daily
SELECT activity_date, steps
FROM bq.mart_steps_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 90 DAY
ORDER BY activity_date
```

<BarChart
  data={steps_daily}
  x=activity_date
  y=steps
  title="日次歩数（直近90日）"
  yAxisTitle="歩"
>
  <ReferenceLine y=10000 label="目標: 10,000歩" color=green />
</BarChart>

## 週次平均

```sql steps_weekly
SELECT
  DATE_TRUNC(activity_date, WEEK(MONDAY)) AS week_start,
  AVG(steps)                              AS avg_steps,
  SUM(steps)                              AS total_steps
FROM bq.mart_steps_daily
GROUP BY 1
ORDER BY 1
```

<LineChart
  data={steps_weekly}
  x=week_start
  y=avg_steps
  title="週次平均歩数"
  yAxisTitle="歩"
>
  <ReferenceLine y=10000 label="目標: 10,000歩" color=green />
</LineChart>
