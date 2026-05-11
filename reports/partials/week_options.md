<script>
  // 直近 26 週分の Sunday-start 週リストを同期生成する。
  // Evidence の Dropdown は最初に登録されたオプションを selectFirst するので、
  // ここで配列の先頭を最新週にしておけば確実に最新週がデフォルト選択される。
  // 既定週の切り替わりは月曜起点。日曜日は新週に切り替わると 1 日分しか
  // データがなく空ボードに見えるため、日曜のうちは前週を既定にする。
  // 「今日」は必ず JST で評価する。SSR は UTC で走るので素の new Date() を
  // 使うと、JST 月曜の早朝ビルドでは UTC ではまだ日曜と判定されてしまい、
  // 既定週が前週に固定されてしまう（SSR で確定した値は CSR でも継続する）。
  const _jstYmd = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' });
  const [_y, _m, _d] = _jstYmd.split('-').map(Number);
  const _today = new Date(_y, _m - 1, _d);
  const _sunday = new Date(_today);
  const _shift = _today.getDay() === 0 ? 7 : _today.getDay();
  _sunday.setDate(_today.getDate() - _shift);
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
