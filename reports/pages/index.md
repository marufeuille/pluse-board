---
title: Home
sidebar_position: 1
---

# ダッシュボード サマリー

```sql latest_streak
SELECT exercise_streak
FROM bq.mart_exercise_streak
ORDER BY activity_date DESC
LIMIT 1
```

```sql current_week_kpi
SELECT
  SUM(duration_minutes) AS current_week_min
FROM bq.mart_exercise_daily
WHERE activity_date >= DATE_SUB(CURRENT_DATE('Asia/Tokyo'), INTERVAL 6 DAY)
```

```sql latest_steps
WITH today_or_yesterday AS (
  SELECT activity_date, steps
  FROM bq.mart_steps_daily
  ORDER BY activity_date DESC
  LIMIT 1
),
last_week AS (
  SELECT steps AS last_week_steps
  FROM bq.mart_steps_daily
  WHERE activity_date = (SELECT DATE_SUB(activity_date, INTERVAL 7 DAY) FROM today_or_yesterday)
)
SELECT
  t.activity_date,
  t.steps,
  l.last_week_steps,
  CASE WHEN l.last_week_steps > 0 THEN (t.steps - l.last_week_steps) / l.last_week_steps ELSE 0 END AS wow_pct
FROM today_or_yesterday t
LEFT JOIN last_week l ON TRUE
```

<div style="display: flex; gap: 1rem; margin-bottom: 2rem;">
  <BigValue data={latest_streak} value=exercise_streak title="連続運動日数" fmt="#,##0 日" />
  <BigValue data={latest_steps} value=steps title="最新の歩数" fmt="#,##0" comparison=wow_pct />
  <BigValue data={current_week_kpi} value=current_week_min title="直近7日間の運動（分）" fmt="#,##0" />
</div>

---

# 週次レポート

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
  COALESCE(SUM(CASE WHEN category = 'その他運動'     THEN duration_minutes END), 0) AS other_min,
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
<BigValue data={week_kpi} value=other_min      title="その他運動（分）"       fmt="#,##0" />
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
  SELECT '筋トレ'         UNION ALL
  SELECT 'その他運動'
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

<LineChart
  data={acwr_in_week}
  x=activity_date
  y=acwr
  title="ACWR（7日平均 ÷ 28日平均）"
  yAxisTitle="ACWR"
  yMin=0
  yMax={Math.max(1.7, ...acwr_in_week.map(d => (d.acwr ?? 0) * 1.1))}
  markers=true
>
  {@partial "acwr_reference_lines.md"}
</LineChart>
{@partial "acwr_reference_legend.md"}

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
    SUM(CASE WHEN category = '筋トレ'         THEN duration_minutes END) AS strength_min,
    SUM(CASE WHEN category = 'その他運動'     THEN duration_minutes END) AS other_min
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
  COALESCE(ex.other_min, 0)          AS "その他運動(分)",
  COALESCE(ex.walk_min, 0) + COALESCE(ex.power_walk_min, 0)
    + COALESCE(ex.strength_min, 0) + COALESCE(ex.other_min, 0)
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
  <Column id="その他運動(分)"      contentType=colorscale colorScale=purples />
  <Column id="合計(分)" />
  <Column id="負荷量(AZM)"         contentType=colorscale colorScale=reds />
  <Column id=ACWR                  fmt="0.00" />
</DataTable>

---

[週次比較ページへ →](/compare) ・ 詳細: [運動の推移](/exercise) ・ [歩数](/steps) ・ [ACWR](/acwr) ・ [指標の定義](/about)
