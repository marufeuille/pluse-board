---
title: Home
sidebar_position: 1
---

# Pluse Board — 週次レポート

{@partial "week_options.md"}

<Dropdown name=selected_week title="週を選択">
  {#each weekOptions as w}
    <DropdownOption value={w.week_start} valueLabel={w.week_label} />
  {/each}
</Dropdown>

```sql week_kpi
SELECT
  COALESCE(SUM(CASE WHEN category = 'ウォーキング'   THEN duration_minutes END), 0) AS walk_min,
  COALESCE(SUM(CASE WHEN category = 'パワーウォーク' THEN duration_minutes END), 0) AS power_walk_min,
  COALESCE(SUM(CASE WHEN category = '筋トレ'         THEN duration_minutes END), 0) AS strength_min,
  COALESCE(SUM(duration_minutes), 0)                                                AS total_min
FROM bq.mart_exercise_daily_categorized
WHERE activity_date BETWEEN CAST('${inputs.selected_week.value}' AS DATE)
                        AND CAST('${inputs.selected_week.value}' AS DATE) + INTERVAL 6 DAY
```

```sql week_load
SELECT
  COALESCE(SUM(load), 0)                          AS total_load,
  ROUND(AVG(acwr), 2)                             AS avg_acwr,
  (
    SELECT ROUND(acwr, 2) FROM bq.mart_acwr
    WHERE d BETWEEN CAST('${inputs.selected_week.value}' AS DATE)
                AND CAST('${inputs.selected_week.value}' AS DATE) + INTERVAL 6 DAY
      AND acwr IS NOT NULL
    ORDER BY d DESC LIMIT 1
  )                                               AS latest_acwr
FROM bq.mart_acwr
WHERE d BETWEEN CAST('${inputs.selected_week.value}' AS DATE)
            AND CAST('${inputs.selected_week.value}' AS DATE) + INTERVAL 6 DAY
```

<BigValue data={week_kpi} value=total_min      title="運動時間 合計（分）"   fmt="#,##0" />
<BigValue data={week_kpi} value=walk_min       title="ウォーキング（分）"     fmt="#,##0" />
<BigValue data={week_kpi} value=power_walk_min title="パワーウォーク（分）"   fmt="#,##0" />
<BigValue data={week_kpi} value=strength_min   title="筋トレ（分）"           fmt="#,##0" />
<BigValue data={week_load} value=total_load    title="負荷量 合計（AZM）"     fmt="#,##0" />
<BigValue data={week_load} value=latest_acwr   title="週末 ACWR"              fmt="0.00" />

## 日別の運動時間（種目ごと）

```sql daily_categorized
WITH days AS (
  SELECT (CAST('${inputs.selected_week.value}' AS DATE) + i * INTERVAL 1 DAY)::DATE AS day
  FROM range(7) t(i)
),
categories AS (
  SELECT 'ウォーキング'   AS category UNION ALL
  SELECT 'パワーウォーク' UNION ALL
  SELECT '筋トレ'
),
matrix AS (
  SELECT day AS activity_date, category FROM days CROSS JOIN categories
)
SELECT
  m.activity_date,
  m.category,
  COALESCE(d.duration_minutes, 0) AS duration_minutes
FROM matrix m
LEFT JOIN bq.mart_exercise_daily_categorized d
  ON m.activity_date = d.activity_date AND m.category = d.category
ORDER BY m.activity_date, m.category
```

<BarChart
  data={daily_categorized}
  x=activity_date
  y=duration_minutes
  series=category
  type=stacked
  title="日別運動時間（種目別、分）"
  yAxisTitle="分"
/>

## 日別の負荷量（AZM）

```sql daily_load
WITH days AS (
  SELECT (CAST('${inputs.selected_week.value}' AS DATE) + i * INTERVAL 1 DAY)::DATE AS day
  FROM range(7) t(i)
)
SELECT
  d.day                AS activity_date,
  COALESCE(l.load, 0)  AS load
FROM days d
LEFT JOIN bq.mart_load_daily l ON d.day = l.activity_date
ORDER BY d.day
```

<BarChart
  data={daily_load}
  x=activity_date
  y=load
  title="日別負荷量（Active Zone Minutes）"
  yAxisTitle="AZM"
/>

## ACWR の推移

```sql acwr_in_week
WITH days AS (
  SELECT (CAST('${inputs.selected_week.value}' AS DATE) + i * INTERVAL 1 DAY)::DATE AS day
  FROM range(7) t(i)
)
SELECT
  d.day                    AS activity_date,
  ROUND(a.acwr, 2)         AS acwr,
  ROUND(a.acute_7d, 1)     AS acute_7d,
  ROUND(a.chronic_28d, 1)  AS chronic_28d
FROM days d
LEFT JOIN bq.mart_acwr a ON d.day = a.d
ORDER BY d.day
```

```sql acwr_bounds
SELECT GREATEST(COALESCE(MAX(acwr), 0) * 1.1, 1.7) AS y_max
FROM acwr_in_week
```

<LineChart
  data={acwr_in_week}
  x=activity_date
  y=acwr
  title="ACWR（7日平均 ÷ 28日平均）"
  yAxisTitle="ACWR"
  yMin=0
  yMax={acwr_bounds[0].y_max}
>
  {@partial "acwr_reference_lines.md"}
</LineChart>

## サマリ表

```sql daily_table
WITH days AS (
  SELECT (CAST('${inputs.selected_week.value}' AS DATE) + i * INTERVAL 1 DAY)::DATE AS day
  FROM range(7) t(i)
),
ex AS (
  SELECT
    activity_date,
    SUM(CASE WHEN category = 'ウォーキング'   THEN duration_minutes END) AS walk_min,
    SUM(CASE WHEN category = 'パワーウォーク' THEN duration_minutes END) AS power_walk_min,
    SUM(CASE WHEN category = '筋トレ'         THEN duration_minutes END) AS strength_min
  FROM bq.mart_exercise_daily_categorized
  WHERE activity_date BETWEEN CAST('${inputs.selected_week.value}' AS DATE)
                          AND CAST('${inputs.selected_week.value}' AS DATE) + INTERVAL 6 DAY
  GROUP BY 1
)
SELECT
  d.day AS 日付,
  CASE EXTRACT('dow' FROM d.day)
    WHEN 0 THEN '日' WHEN 1 THEN '月' WHEN 2 THEN '火'
    WHEN 3 THEN '水' WHEN 4 THEN '木' WHEN 5 THEN '金' WHEN 6 THEN '土'
  END                                AS 曜日,
  COALESCE(ex.walk_min, 0)           AS "ウォーキング(分)",
  COALESCE(ex.power_walk_min, 0)     AS "パワーウォーク(分)",
  COALESCE(ex.strength_min, 0)       AS "筋トレ(分)",
  COALESCE(ex.walk_min, 0) + COALESCE(ex.power_walk_min, 0) + COALESCE(ex.strength_min, 0)
                                     AS "合計(分)",
  COALESCE(a.load, 0)                AS "負荷量(AZM)",
  ROUND(a.acwr, 2)                   AS ACWR
FROM days d
LEFT JOIN ex             ON d.day = ex.activity_date
LEFT JOIN bq.mart_acwr a ON d.day = a.d
ORDER BY d.day
```

<DataTable data={daily_table} totalRow=true>
  <Column id=日付 />
  <Column id=曜日 align=center />
  <Column id="ウォーキング(分)"   contentType=colorscale colorScale=blues />
  <Column id="パワーウォーク(分)" contentType=colorscale colorScale=greens />
  <Column id="筋トレ(分)"          contentType=colorscale colorScale=oranges />
  <Column id="合計(分)" />
  <Column id="負荷量(AZM)"         contentType=colorscale colorScale=reds />
  <Column id=ACWR                  fmt="0.00" />
</DataTable>

---

[週次比較ページへ →](/compare) ・ 詳細ページ: [運動の推移](/exercise) ・ [歩数](/steps) ・ [ACWR](/acwr)
