---
title: ACWR
sidebar_position: 3
---

# ACWR（Acute:Chronic Workload Ratio）

ACWR = 直近7日の平均日次負荷 ÷ 直近28日の平均日次負荷。

- **0.8 〜 1.3**: 適切な負荷ゾーン（緑）
- **1.5 超**: 過負荷ゾーン（赤）。怪我リスクが高まる。
- **0.8 未満**: 負荷不足ゾーン（体力低下の可能性）

> 計算式の詳細・休養日0埋めの扱いなどは [指標の定義](/about) を参照。

```sql acwr_data
SELECT
  d           AS activity_date,
  load,
  acute_7d,
  chronic_28d,
  acwr
FROM bq.mart_acwr
WHERE d >= CURRENT_DATE - INTERVAL 90 DAY
ORDER BY d
```

```sql acwr_bounds
SELECT GREATEST(MAX(acwr) * 1.1, 1.7) AS y_max
FROM bq.mart_acwr
WHERE d >= CURRENT_DATE - INTERVAL 90 DAY
```

<LineChart
  data={acwr_data}
  x=activity_date
  y=acwr
  title="ACWR の推移（直近90日）"
  yAxisTitle="ACWR"
  yMin=0
  yMax={acwr_bounds[0].y_max}
>
  {@partial "acwr_reference_lines.md"}
</LineChart>
{@partial "acwr_reference_legend.md"}

## 日次負荷の推移

```sql load_data
SELECT
  d           AS activity_date,
  load,
  acute_7d    AS acute_7d_avg,
  chronic_28d AS chronic_28d_avg
FROM bq.mart_acwr
WHERE d >= CURRENT_DATE - INTERVAL 90 DAY
ORDER BY d
```

<BarChart
  data={load_data}
  x=activity_date
  y=load
  title="日次アクティブゾーン分"
  yAxisTitle="分"
/>

<LineChart
  data={load_data}
  x=activity_date
  y={["acute_7d_avg", "chronic_28d_avg"]}
  title="7日平均 vs 28日平均"
  yAxisTitle="分"
/>
