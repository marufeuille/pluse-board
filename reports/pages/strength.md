---
title: 筋トレ
sidebar_position: 5
---

# 筋トレ

有酸素向けの ACWR は心拍ベースの AZM（Active Zone Minutes）を負荷にしているため、
セット間レストで心拍が上がりきらない**筋トレでは負荷がほとんど立たない**。
そこで筋トレは「頻度・時間・連続達成（ストリーク）」で別軸に追う。
**週3回以上**のセッションを満たした週を「達成週」とし、達成週が連続した数をストリークとする。

```sql streak
SELECT current_streak_weeks, best_streak_weeks
FROM bq.mart_strength_streak
```

```sql last30
SELECT
  COALESCE(SUM(session_count), 0)    AS sessions_30d,
  COALESCE(SUM(duration_minutes), 0) AS minutes_30d,
  COALESCE(SUM(calories_kcal), 0)    AS calories_30d
FROM bq.mart_strength_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 30 DAY
```

<BigValue data={streak} value=current_streak_weeks title="現在のストリーク（週）"   fmt="#,##0" />
<BigValue data={streak} value=best_streak_weeks    title="ベストストリーク（週）" fmt="#,##0" />
<BigValue data={last30} value=sessions_30d         title="直近30日のセッション数" fmt="#,##0" />
<BigValue data={last30} value=minutes_30d          title="直近30日の筋トレ（分）" fmt="#,##0" />

## 週次の頻度（達成＝週3回以上）

```sql weekly
SELECT
  week_start,
  sessions,
  active_days,
  duration_minutes,
  calories_kcal,
  meets_target
FROM bq.mart_strength_weekly
WHERE week_start >= CURRENT_DATE - INTERVAL 180 DAY
ORDER BY week_start
```

<BarChart
  data={weekly}
  x=week_start
  y=sessions
  title="週次セッション数"
  yAxisTitle="回"
>
  <ReferenceLine y=3 label="達成ライン: 週3回" color=green />
</BarChart>

## 週次の筋トレ時間

<BarChart
  data={weekly}
  x=week_start
  y=duration_minutes
  title="週次筋トレ時間"
  yAxisTitle="分"
/>

## 週次の消費カロリー（Fitbit 推定）

<BarChart
  data={weekly}
  x=week_start
  y=calories_kcal
  title="週次筋トレ由来カロリー"
  yAxisTitle="kcal"
/>

## 日次の筋トレ時間（直近90日）

```sql daily
SELECT
  activity_date,
  duration_minutes,
  session_count
FROM bq.mart_strength_daily
WHERE activity_date >= CURRENT_DATE - INTERVAL 90 DAY
ORDER BY activity_date
```

<BarChart
  data={daily}
  x=activity_date
  y=duration_minutes
  title="日次筋トレ時間（直近90日）"
  yAxisTitle="分"
/>

---

詳細: [運動の推移](/exercise) ・ [ACWR](/acwr) ・ [歩数](/steps) ・ [指標の定義](/about)
