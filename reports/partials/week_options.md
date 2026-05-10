<script>
  // 直近 26 週分の Sunday-start 週リストを同期生成する。
  // Evidence の Dropdown は最初に登録されたオプションを selectFirst するので、
  // ここで配列の先頭を最新週にしておけば確実に最新週がデフォルト選択される。
  const _today = new Date();
  const _sunday = new Date(_today);
  _sunday.setDate(_today.getDate() - _today.getDay());
  const _fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const _mmdd = (d) => `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const weekOptions = Array.from({ length: 26 }, (_, i) => {
    const start = new Date(_sunday);
    start.setDate(_sunday.getDate() - i * 7);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return {
      week_start: _fmt(start),
      week_label: `${_fmt(start)} 〜 ${_mmdd(end)}`
    };
  });
</script>
