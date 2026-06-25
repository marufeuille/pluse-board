# beads 導入設計 — pluse-board（リポジトリ内完結 + DoltHub 同期）

## Context

pluse-board の機能開発・バグ・タスクを [beads](https://github.com/gastownhall/beads)（`bd` CLI、Dolt バックエンドの分散型イシュートラッカー）で管理する。タスクは pluse-board リポジトリ内の `.beads/`（ローカル Dolt DB）を SSOT とし、**DoltHub リモート**でローカル Claude Code と CI 間で同期する。

**ゴール:**
- Claude Code が `bd` コマンドでタスクを読み書きできる
- DoltHub 経由でローカルと CI を同期（Web UI でタスクをブラウズ・SQL クエリ可能）
- Daily Build 失敗時、CI から beads に自動起票する（既存 GitHub issue と並存）

## 方針の変遷（当初案 → 採用案）

当初は中央 hub リポジトリ（`tasks-hub`）+ Cloudflare Workers でクロスリポジトリ一元管理を想定していたが、以下の理由で **pluse-board リポジトリ内完結** に変更した。

- 「他リポジトリのタスクを pluse-board に置くのは変」→ 各リポジトリが自分の `.beads/` を持つ（bd 本来の分散モデル）
- 中央 hub・クロスリポジトリ共有・Cloudflare Workers は将来フェーズへ

## アーキテクチャ

```
ローカル Claude Code                    GitHub Actions (CI)
  bd create / bd close                    bd bootstrap --yes
  bd dolt pull / push        ⇕            bd create (Daily Build failure)
       │                                   bd dolt push
       └──────── DoltHub リモート ────────────┘
            dolthub.com/marufeuille/pluse-board
             （Dolt データの SSOT・Web UI 付き）
```

- **SSOT は DoltHub 上の Dolt リモート**（`marufeuille/pluse-board`）。
- CI は pluse-board の **git ワーキングツリーに触れない**（DoltHub のみ更新）→ AGENTS.md の「main へ直接 push 禁止」ルールと衝突しない。
- Dolt のセルレベルマージで並行書き込みを自動解決。

## 実機確認による修正（当初設計 → 採用）

| 当初案 | 実機確認（bd 1.0.4） | 採用 |
|---|---|---|
| `~/.config/bd/config.yaml` の `beads_dir:` グローバル設定 | **存在しない**。`bd config` は per-project | リポジトリルート `.beads/` を使用 |
| `brew install gastownhall/tap/bd` | 既存 `~/.local/bin/bd` で不要 | brew 手順は廃止 |
| npm `@gastownhall/bd` | 実際は `@beads/bd` | CI は `npm install -g @beads/bd` |
| Dolt リモート URL `https://dolthub.com/...` | `rpc error: Unimplemented`（一般 https と誤認） | **`marufeuille/pluse-board`（owner/repo 形式が必須）** |
| 同期方式が未指定 | `bd dolt push`/`pull` + `bd bootstrap` | DoltHub（Hosted Dolt） |

## コンポーネント

### 1. beads 初期化（ローカル・PR-1）
- `bd init --non-interactive --role maintainer` が `.beads/`、git hooks、`.claude/settings.json`、AGENTS.md への統合セクションを一括生成する。
- `.beads/.gitignore`（bd 生成）が Dolt DB（`embeddeddolt/`）を除外し、`config.yaml` / `metadata.json` / `issues.jsonl` を追跡する。
- ルート `.gitignore` に `.dolt/` / `*.db` / `.beads-credential-key` を追加。

### 2. Claude Code 統合（PR-1）
- `.claude/settings.json` に SessionStart / PreCompact hooks を登録（`bd prime` でワークフロー文脈を注入）。
- `AGENTS.md` に Issue Tracking セクション（bd コマンド群・DoltHub 同期手順）を追記。
- `CLAUDE.md` は作成しない（`AGENTS.md` を SSOT とする）。

### 3. DoltHub リモート（PR-1）
- `bd dolt remote add origin marufeuille/pluse-board`（owner/repo 形式が必須）。
- `bd config set sync.remote marufeuille/pluse-board` で `.beads/config.yaml` に永続化（CI / clone での共有用）。`bd dolt remote add` だけでは DB 内にしか保存されず git で共有されないため、この手順が必須。
- `bd dolt push` で DoltHub に公開。別環境は `bd bootstrap --yes` が `sync.remote` から自動復元する。

### 4. CI 自動起票（Daily Build 失敗・PR-2）
- `.github/workflows/daily-build-triage.yml` に `create_beads_issue` ジョブを追加（既存 `report_manual` の GitHub issue 作成は維持）。
- フロー: `bd bootstrap`（DoltHub から復元）→ `bd create`（分類本文付き）→ `bd dolt push`。
- CI Secrets: `DOLT_REMOTE_USER` / `DOLT_REMOTE_PASSWORD`（push 競合時は `bd dolt pull --force` → 再 push でリトライ）。

## 並行アクセスについて

| ケース | 対処 |
|---|---|
| 個人 + 手作業 | 直列なので問題なし |
| CI が稀に重なる | Dolt のセルレベルマージ + `bd dolt push \|\| (bd dolt pull --force && bd dolt push)` の retry |
| 本格的な並行書き込みが必要 | `bd init --server` + dolt sql-server（将来フェーズ） |

## コスト試算

| コンポーネント | サービス | 月額 |
|---|---|---|
| beads ローカル DB | Dolt（embedded） | $0 |
| Dolt リモート | DoltHub（無料枠・プライベート） | $0 |
| CI 実行 | GitHub Actions（無料枠） | $0 |
| **合計** | | **$0** |

> issue データ（JSON）は小さいため DoltHub 無料枠で充分。肥大化時は `bd gc` / `bd compact` / `bd prune` で整理。

## 検証済み（PR-1）

- ローカル `bd create` → `bd dolt push` → 別ディレクトリに clone → `bd bootstrap --yes`（DoltHub から 93 chunks 復元）→ issue 復元 → `bd delete --force` → `bd dolt push` のラウンドトリップを確認。

## 範囲外（将来フェーズ）

- 中央 hub リポジトリ（`tasks-hub`）/ クロスリポジトリタスク共有（`BEADS_DIR` 参照・federation）
- Cloudflare Workers（GitHub webhook 受信 → 自動起票の多リポジトリ化・Slack 連携）
- pluse-board の git refs（`refs/dolt/data`）をリモートにする方式（DoltHub 不採用時のフォールバック候補）
