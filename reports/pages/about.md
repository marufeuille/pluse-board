---
title: 定義
sidebar_position: 6
---

# 用語・計算式の定義

指標の定義。閾値や分類ルールはここを正としており、
SQL 側も同じ値を直接参照している。変える時はここの記述と SQL を一緒に更新する。

## 運動カテゴリ

Google Health API から取得した `exercise.exerciseType` を以下にマッピングして集計している。

| カテゴリ | 判定ルール |
|---|---|
| **筋トレ** | `exerciseType = 'STRENGTH_TRAINING'` |
| **パワーウォーク** | `exerciseType = 'WALKING'` かつ `AZM / 運動時間(分) ≥ 0.5` |
| **ウォーキング** | `exerciseType = 'WALKING'` かつ `AZM / 運動時間(分) < 0.5` |
| その他 | 上記以外の `exerciseType` (`activity_name` をそのまま使用) |

### パワーウォーク判定の意図

「日常の散歩」と「運動目的の早歩き」を区別したい。Fitbit Active Zone Minutes (AZM) は
心拍ベースで「運動として有効な強度の時間」を計測するため、
**AZM / 運動時間が 0.5 以上 = 半分以上の時間が心拍ゾーンに入っていた = 運動目的**
として扱える。

実装: [`dbt_project/models/marts/mart_exercise_daily_categorized.sql`](https://github.com/marufeuille/pluse-board/blob/main/dbt_project/models/marts/mart_exercise_daily_categorized.sql)

## 負荷量 (Load)

`Active Zone Minutes` の日次合計を負荷量として使う。Fitbit が定義する
「中〜高強度の心拍ゾーンに入っていた分数」をそのまま採用。

実装: [`dbt_project/models/marts/mart_load_daily.sql`](https://github.com/marufeuille/pluse-board/blob/main/dbt_project/models/marts/mart_load_daily.sql)

## ACWR (Acute:Chronic Workload Ratio)

    ACWR = 直近 7 日の平均日次負荷 / 直近 28 日の平均日次負荷

スポーツ科学で広く使われる怪我リスクの指標。「最近の急な負荷」と「ここ1ヶ月の慣れた負荷」の比。

| 帯域 | 解釈 |
|---|---|
| **0.8 〜 1.3** | 適切ゾーン (緑) |
| **1.5 超** | 過負荷ゾーン (赤)。怪我リスクが高まる。 |
| **0.8 未満** | 負荷不足ゾーン (体力低下の可能性) |

### 実装上の注意

- **休養日は 0 埋め必須**: 運動した日だけで rolling 平均を取ると ACWR が過大評価される。
  calendar JOIN で全日付を埋めて 0 として扱う。
- **chronic 28 日窓が揃わない期間は NULL**: データ初期は 28 日に達しないため
  ACWR を計算しない (`COUNT(*) OVER ... < 28` で判定)。

実装: [`dbt_project/models/marts/mart_acwr.sql`](https://github.com/marufeuille/pluse-board/blob/main/dbt_project/models/marts/mart_acwr.sql)

## 週の区切り

すべての週次集計は **日曜はじまり** で統一。

    DATE_TRUNC(activity_date, WEEK(SUNDAY))   -- BigQuery
    activity_date - dayofweek(activity_date) * INTERVAL 1 DAY   -- DuckDB (Evidence ページ内)
