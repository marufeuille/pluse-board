AUDIT (name assert_interval_not_empty, blocking := true);

-- 処理されたインターバルに行が1件もない場合に失敗する。
-- 行を返す = 失敗、行なし = 成功（SQLMesh audit の規約）。
SELECT 1
FROM (
  SELECT COUNT(*) AS cnt
  FROM @this_model
  WHERE activity_date BETWEEN @start_ds AND @end_ds
)
WHERE cnt = 0
