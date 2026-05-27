---
title: Compare
sidebar_position: 2
---

# 週次比較

{@partial "week_options.md"}

<Dropdown name=base_week title="基準週 (A)">
  {#each weekOptions as w}
    <DropdownOption value={w.week_start} valueLabel={w.week_label} />
  {/each}
</Dropdown>

<Dropdown name=compare_week title="比較週 (B)">
  {#each weekOptions.slice(1) as w}
    <DropdownOption value={w.week_start} valueLabel={w.week_label} />
  {/each}
</Dropdown>

```sql kpi_compare
WITH base_dt AS (
  SELECT CAST('${inputs.base_week.value}' AS DATE) AS ws
),
comp_dt AS (
  SELECT CAST('${inputs.compare_week.value}' AS DATE) AS ws
),
ex_a AS (
  SELECT
    COALESCE(SUM(CASE WHEN category = 'ウォーキング'   THEN duration_minutes END), 0) AS walk,
    COALESCE(SUM(CASE WHEN category = 'パワーウォーク' THEN duration_minutes END), 0) AS power_walk,
    COALESCE(SUM(CASE WHEN category = '筋トレ'         THEN duration_minutes END), 0) AS strength,
    COALESCE(SUM(CASE WHEN category = 'その他運動'     THEN duration_minutes END), 0) AS other,
    COALESCE(SUM(duration_minutes), 0)                                                AS total
  FROM bq.mart_exercise_daily_categorized m, base_dt
  WHERE m.activity_date BETWEEN base_dt.ws AND base_dt.ws + 6
),
ex_b AS (
  SELECT
    COALESCE(SUM(CASE WHEN category = 'ウォーキング'   THEN duration_minutes END), 0) AS walk,
    COALESCE(SUM(CASE WHEN category = 'パワーウォーク' THEN duration_minutes END), 0) AS power_walk,
    COALESCE(SUM(CASE WHEN category = '筋トレ'         THEN duration_minutes END), 0) AS strength,
    COALESCE(SUM(CASE WHEN category = 'その他運動'     THEN duration_minutes END), 0) AS other,
    COALESCE(SUM(duration_minutes), 0)                                                AS total
  FROM bq.mart_exercise_daily_categorized m, comp_dt
  WHERE m.activity_date BETWEEN comp_dt.ws AND comp_dt.ws + 6
),
load_a AS (
  SELECT
    COALESCE(SUM(load), 0)                            AS total_load,
    (SELECT ROUND(acwr, 2) FROM bq.mart_acwr a, base_dt b
     WHERE a.d BETWEEN b.ws AND b.ws + 6 AND acwr IS NOT NULL
     ORDER BY a.d DESC LIMIT 1)                       AS latest_acwr
  FROM bq.mart_acwr m, base_dt
  WHERE m.d BETWEEN base_dt.ws AND base_dt.ws + 6
),
load_b AS (
  SELECT
    COALESCE(SUM(load), 0)                            AS total_load,
    (SELECT ROUND(acwr, 2) FROM bq.mart_acwr a, comp_dt b
     WHERE a.d BETWEEN b.ws AND b.ws + 6 AND acwr IS NOT NULL
     ORDER BY a.d DESC LIMIT 1)                       AS latest_acwr
  FROM bq.mart_acwr m, comp_dt
  WHERE m.d BETWEEN comp_dt.ws AND comp_dt.ws + 6
)
SELECT
  ex_a.walk         AS walk_a,         ex_b.walk         AS walk_b,
  ex_a.power_walk   AS power_walk_a,   ex_b.power_walk   AS power_walk_b,
  ex_a.strength     AS strength_a,     ex_b.strength     AS strength_b,
  ex_a.other        AS other_a,        ex_b.other        AS other_b,
  ex_a.total        AS total_a,        ex_b.total        AS total_b,
  load_a.total_load AS load_a,         load_b.total_load AS load_b,
  load_a.latest_acwr AS acwr_a,        load_b.latest_acwr AS acwr_b
FROM ex_a, ex_b, load_a, load_b
```

## KPI 比較 (A: 基準週、Δ: 比較週との差)

<BigValue data={kpi_compare} value=total_a       comparison=total_b       title="運動時間 合計（分）"   fmt="#,##0" />
<BigValue data={kpi_compare} value=walk_a        comparison=walk_b        title="ウォーキング（分）"     fmt="#,##0" />
<BigValue data={kpi_compare} value=power_walk_a  comparison=power_walk_b  title="パワーウォーク（分）"   fmt="#,##0" />
<BigValue data={kpi_compare} value=strength_a    comparison=strength_b    title="筋トレ（分）"           fmt="#,##0" />
<BigValue data={kpi_compare} value=other_a       comparison=other_b       title="その他運動（分）"       fmt="#,##0" />
<BigValue data={kpi_compare} value=load_a        comparison=load_b        title="負荷量 合計（AZM）"     fmt="#,##0" />
<BigValue data={kpi_compare} value=acwr_a        comparison=acwr_b        title="週末 ACWR"              fmt="0.00" />

## 曜日別の運動時間

```sql dow_exercise
WITH base_dt AS (
  SELECT CAST('${inputs.base_week.value}' AS DATE) AS ws
),
comp_dt AS (
  SELECT CAST('${inputs.compare_week.value}' AS DATE) AS ws
),
days AS (
  SELECT
    i AS day_offset,
    CASE i WHEN 0 THEN '日' WHEN 1 THEN '月' WHEN 2 THEN '火'
           WHEN 3 THEN '水' WHEN 4 THEN '木' WHEN 5 THEN '金'
           WHEN 6 THEN '土' END AS dow
  FROM range(7) t(i)
),
weeks AS (
  SELECT 'A' AS week_id, '基準週 (A)' AS week_label, ws AS week_start FROM base_dt
  UNION ALL
  SELECT 'B' AS week_id, '比較週 (B)' AS week_label, ws AS week_start FROM comp_dt
),
categories AS (
  SELECT 'ウォーキング'   AS category UNION ALL
  SELECT 'パワーウォーク' UNION ALL
  SELECT '筋トレ'         UNION ALL
  SELECT 'その他運動'
),
matrix AS (
  SELECT
    d.day_offset, d.dow,
    w.week_id, w.week_label,
    c.category,
    (w.week_start + d.day_offset * INTERVAL 1 DAY)::DATE AS activity_date
  FROM days d CROSS JOIN weeks w CROSS JOIN categories c
)
SELECT
  m.day_offset,
  m.dow,
  m.week_id,
  m.week_label,
  m.category,
  COALESCE(d.duration_minutes, 0) AS minutes
FROM matrix m
LEFT JOIN bq.mart_exercise_daily_categorized d
  ON m.activity_date = d.activity_date
  AND m.category = d.category
ORDER BY m.day_offset, m.week_id, m.category
```

### ウォーキング

<BarChart
  data={dow_exercise.where(`category = 'ウォーキング'`)}
  x=dow
  y=minutes
  series=week_label
  type=grouped
  sort=false
  title="ウォーキング (曜日別、分)"
  yAxisTitle="分"
/>

### パワーウォーク

<BarChart
  data={dow_exercise.where(`category = 'パワーウォーク'`)}
  x=dow
  y=minutes
  series=week_label
  type=grouped
  sort=false
  title="パワーウォーク (曜日別、分)"
  yAxisTitle="分"
/>

### 筋トレ

<BarChart
  data={dow_exercise.where(`category = '筋トレ'`)}
  x=dow
  y=minutes
  series=week_label
  type=grouped
  sort=false
  title="筋トレ (曜日別、分)"
  yAxisTitle="分"
/>

### その他運動

<BarChart
  data={dow_exercise.where(`category = 'その他運動'`)}
  x=dow
  y=minutes
  series=week_label
  type=grouped
  sort=false
  title="その他運動 (曜日別、分)"
  yAxisTitle="分"
/>

## 曜日別の負荷量 (AZM)

```sql dow_load
WITH base_dt AS (
  SELECT CAST('${inputs.base_week.value}' AS DATE) AS ws
),
comp_dt AS (
  SELECT CAST('${inputs.compare_week.value}' AS DATE) AS ws
),
days AS (
  SELECT
    i AS day_offset,
    CASE i WHEN 0 THEN '日' WHEN 1 THEN '月' WHEN 2 THEN '火'
           WHEN 3 THEN '水' WHEN 4 THEN '木' WHEN 5 THEN '金'
           WHEN 6 THEN '土' END AS dow
  FROM range(7) t(i)
),
weeks AS (
  SELECT '基準週 (A)' AS week_label, ws AS week_start FROM base_dt
  UNION ALL
  SELECT '比較週 (B)' AS week_label, ws AS week_start FROM comp_dt
),
matrix AS (
  SELECT d.day_offset, d.dow, w.week_label,
         (w.week_start + d.day_offset * INTERVAL 1 DAY)::DATE AS activity_date
  FROM days d CROSS JOIN weeks w
)
SELECT
  m.day_offset,
  m.dow,
  m.week_label,
  COALESCE(l.load, 0) AS load
FROM matrix m
LEFT JOIN bq.mart_load_daily l ON m.activity_date = l.activity_date
ORDER BY m.day_offset, m.week_label
```

<BarChart
  data={dow_load}
  x=dow
  y=load
  series=week_label
  type=grouped
  sort=false
  title="負荷量 (曜日別、AZM)"
  yAxisTitle="AZM"
/>

## 曜日別の ACWR

```sql dow_acwr
WITH base_dt AS (
  SELECT CAST('${inputs.base_week.value}' AS DATE) AS ws
),
comp_dt AS (
  SELECT CAST('${inputs.compare_week.value}' AS DATE) AS ws
),
days AS (
  SELECT
    i AS day_offset,
    CASE i WHEN 0 THEN '日' WHEN 1 THEN '月' WHEN 2 THEN '火'
           WHEN 3 THEN '水' WHEN 4 THEN '木' WHEN 5 THEN '金'
           WHEN 6 THEN '土' END AS dow
  FROM range(7) t(i)
),
weeks AS (
  SELECT '基準週 (A)' AS week_label, ws AS week_start FROM base_dt
  UNION ALL
  SELECT '比較週 (B)' AS week_label, ws AS week_start FROM comp_dt
),
matrix AS (
  SELECT d.day_offset, d.dow, w.week_label,
         (w.week_start + d.day_offset * INTERVAL 1 DAY)::DATE AS activity_date
  FROM days d CROSS JOIN weeks w
)
SELECT
  m.day_offset,
  m.dow,
  m.week_label,
  ROUND(a.acwr, 2) AS acwr
FROM matrix m
LEFT JOIN bq.mart_acwr a ON m.activity_date = a.d
ORDER BY m.day_offset, m.week_label
```

<LineChart
  data={dow_acwr}
  x=dow
  y=acwr
  series=week_label
  sort=false
  title="ACWR (曜日別)"
  yAxisTitle="ACWR"
  yMin=0
  yMax={Math.max(1.7, ...dow_acwr.map(d => (d.acwr ?? 0) * 1.1))}
>
  {@partial "acwr_reference_lines.md"}
</LineChart>
{@partial "acwr_reference_legend.md"}

---

[← ホーム週次レポートへ](/) ・ [指標の定義](/about)
