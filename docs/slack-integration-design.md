# Slack → beads 起票 設計（引き継ぎ・別セッション実装用）

## Context

beads 導入は完了済み:
- **PR-1（#34）**: `bd init` + Claude 統合 + DoltHub 同期。SSOT = DoltHub（`marufeuille/pluse-board`）。
- **PR-2（#36）**: Daily Build 失敗時の `create_beads_issue` ジョブ（`.github/workflows/daily-build-triage.yml`）。

本ドキュメントは次フェーズ **「Slack から beads にタスクを起票する経路」** の設計。

> **Status: 実装済み**（feature/slack-beads-create）。前半（Context〜設計メモ）は引き継ぎ時点の設計判断をそのまま残し、後半「実装状態」以降に実装結果・訂正・デプロイ手順を追記。

## 設計判断（確定）

| 判断 | 決定 | 理由 |
|---|---|---|
| Slack 受信 | **Slash Command `/task`** | 明示的、誤爆なし、実装シンプル |
| LLM 構造化 | **GPT（`OPENAI_API_KEY` 再用）** | pluse-board 既存の KEY（Daily Build Codex 用）を流用、新規発行不要 |
| インフラ | **Cloudflare Workers**（HTTP 受け）+ **GitHub Actions**（dispatch 受信） | Slack の HTTP リクエストを受けるエンドポイントが必須。Workers で受け、Actions で `bd` 実行 |

## アーキテクチャ

```
Slack で /task <メッセージ>
  │  Slash Command (HTTP POST, Slack 署名付き)
  ▼
Cloudflare Workers
  ├ Slack 署名検証（SLACK_SIGNING_SECRET）
  ├ 即 ACK（3 秒以内必須）
  ├ GPT で構造化（タイトル/タイプ/優先度/本文）← OPENAI_API_KEY
  └ GitHub repository_dispatch 送信（GH_TOKEN, client_payload）
  ▼
GitHub Actions（pluse-board: .github/workflows/slack-beads-create.yml）
  ├ on.repository_dispatch で起動
  ├ bd bootstrap --yes（DoltHub から復元）← DOLT_CREDS_KEY_ID/JWK
  ├ bd create（構造化データで bug/task/feature を指定）
  ├ bd dolt push
  └ Slack に「起票しました <issue_id>」通知 ← SLACK_BOT_TOKEN
```

## 前提（beads 側は完了済み・再設定不要）

- `.beads/config.yaml` の `sync.remote: marufeuille/pluse-board`（main マージ済み）
- GitHub Secrets: `DOLT_CREDS_KEY_ID`, `DOLT_CREDS_JWK`（CI 認証、設定済み）
- `OPENAI_API_KEY`（Codex 用、設定済み）

## 新規に必要な設定（別セッションで実施）

### 1. Slack App（api.slack.com/apps）
- Slash Command `/task` を作成、Request URL = `https://<workers-subdomain>.workers.dev/slack`
- Bot Token Scopes: `chat:write`（完了通知用）、`commands`（Slash Command）
- **取得して保存**: Signing Secret、Bot Token（`xoxb-...`）

### 2. Cloudflare Workers
- `npm create cloudflare@latest beads-slack` → `wrangler deploy`
- Secrets（`wrangler secret put`）:
  - `SLACK_SIGNING_SECRET`
  - `OPENAI_API_KEY`（GPT 構造化を Workers で行う場合）
  - `GH_TOKEN`（repository_dispatch 送信、fine-grained PAT or `repo` スコープ）
  - `REPO` = `marufeuille/pluse-board`

### 3. GitHub（pluse-board）
- Secrets 追加: `SLACK_BOT_TOKEN`（完了通知用）
- ワークフロー新設: `.github/workflows/slack-beads-create.yml`（`on.repository_dispatch`）

## 実装の分割（別セッション）

1. **GitHub Actions 側**（先に作る・テストしやすい）
   - `.github/workflows/slack-beads-create.yml`: `repository_dispatch` で起動 → `bd bootstrap` → `bd create` → `bd dolt push` → Slack 通知
   - PR-2 の `create_beads_issue` ジョブをほぼ流用（差分: 入力が triage outputs ではなく dispatch payload、Slack 通知ステップ追加）
2. **Cloudflare Workers 側**
   - Slack 署名検証（HMAC-SHA256）→ 即 ACK
   - `waitUntil` で非同期に GPT 構造化 → `repository_dispatch` POST
3. **Slack App 設定**: Slash Command 登録、インストール

## 検証

- Slack で `/task ログイン画面のバグを直して` → GPT が `bug / P1 / タイトル: ログイン画面のバグ修正` に構造化 → DoltHub に `pluse-board-xxx` 起票 → Slack に「起票しました pluse-board-xxx」通知
- 確認項目: Slack 署名検証、repository_dispatch 認証、DoltHub 認証（dolt creds）、LLM 構造化の精度、重複起票の回避

## 設計メモ

- Slack Slash Command は 3 秒以内の ACK が必須 → Workers は即 ACK し、`ctx.waitUntil()` で GPT 呼び出し + dispatch 送信を非同期化。
- GPT 構造化を Workers で行う利点: GitHub 側に `OPENAI_API_KEY` を渡さず Workers Secret で完結（既に GitHub 側にも OPENAI_API_KEY はあるが、責務分離）。Actions 側で構造化する案も可（その場合 dispatch payload に生メッセージを送り Actions で GPT 呼び出し）。
- 完了通知は Bot Token でコマンド実行チャンネル/DM に投稿（`response_url` を使う手も）。
- `daily-build-triage.yml` の `create_beads_issue` と Slack 起票の Actions は、bd 実行部分を共通化（composite action 化）するとよい。

## 実装状態（完了）

実装したファイル:

| ファイル | 役割 |
|---|---|
| `.github/actions/setup-bd/action.yml` | composite action: dolt/bd インストール・DoltHub 認証・bootstrap・pull。`daily-build-triage` と `slack-beads-create` で共用（設計メモの共通化推奨を反映） |
| `.github/workflows/slack-beads-create.yml` | `repository_dispatch`/`workflow_dispatch` で起動 → bd 起票 → DoltHub push → Slack 通知 |
| `.github/workflows/daily-build-triage.yml` | `create_beads_issue` ジョブの bd セットアップを setup-bd 使用に置換（起票ロジックは不変） |
| `workers/beads-slack/` | Cloudflare Worker（TypeScript）: 署名検証 → 即ACK → GPT 構造化 → repository_dispatch |
| `.github/dependabot.yml` | `workers/beads-slack` 向け npm エントリ追加 |

### 設計に対する訂正

- **Slash Command に `message_ts` は含まれない**（message action / shortcut のみ）。重複回避のキーには使えないため、Worker が相関 ID（UUID）を生成して `--external-ref "slack-<id>"` に用いる。主たる重複回避は title ベース（`bd search` の既存パターンを踏襲）。
- event_type = **`slack-task`**。
- 完了通知は Bot Token の `chat.postMessage` を正（永続・全員に可視）。`response_url` は早期ヒントのみ（ephemeral・30分限定）。

### client_payload スキーマ（Worker → Actions）

`title`, `type`(bug|task|feature), `priority`("0"-"4"), `description`, `raw_text`, `channel_id`, `response_url`, `correlation_id`, `user`

### デプロイ手順（ユーザー作業・AGENTS.md 制約）

1. **Slack App**（api.slack.com/apps）: Slash Command `/task`（Request URL = `https://beads-slack.<account>.workers.dev/slack`）、Bot Token Scopes `commands` + `chat:write`。Signing Secret / Bot Token（`xoxb-...`）を取得。
2. **Cloudflare**: `cd workers/beads-slack && npm install` → `npx wrangler secret put SLACK_SIGNING_SECRET` / `OPENAI_API_KEY` / `GH_TOKEN` → `npm run deploy`。
3. **GitHub Secrets**: `marufeuille/pluse-board` に `SLACK_BOT_TOKEN` を追加。`GH_TOKEN` は fine-grained PAT（権限 `Actions: Read and write`、対象リポジトリは pluse-board のみ。**`Contents` 権限では repository_dispatch は 403 になる**）または classic `repo` scope（fine-grained 推奨）。
4. **Slack App インストール**: ワークスペースにインストール。
5. **動作確認**: Slack で `/task ログイン画面のバグを直して` → DoltHub に起票 → Slack に「起票しました <id>」通知。

### Secrets / 変数一覧

| 場所 | キー | 用途 |
|---|---|---|
| Cloudflare secret | `SLACK_SIGNING_SECRET` | 署名検証 |
| Cloudflare secret | `OPENAI_API_KEY` | GPT 構造化（Workers 側） |
| Cloudflare secret | `GH_TOKEN` | repository_dispatch 送信 |
| Cloudflare var | `REPO` | `marufeuille/pluse-board`（`wrangler.toml`） |
| GitHub Secret | `SLACK_BOT_TOKEN` | 完了通知 |
| GitHub Secret（既存） | `DOLT_CREDS_KEY_ID` / `DOLT_CREDS_JWK` | bd 認証（両ワークフロー共用） |
| GitHub Secret（既存） | `OPENAI_API_KEY` | Daily Build Codex 用（Workers とは別管理） |

### 検証

- `./scripts/actionlint`: ワークフロー + composite action の構文検証（CI = PR Check で実行）。
- `cd workers/beads-slack && npm run test`: 署名検証のユニットテスト（vitest・6 cases）。
- **bd パス手動テスト（Worker 不要）**: Actions UI → "Slack Beads Create" → workflow_dispatch で title/type/priority/body 入力 → bd 起票〜DoltHub push を確認。
- **repository_dispatch 直叩き**:
  ```bash
  gh api -X POST repos/marufeuille/pluse-board/dispatches --input - <<'JSON'
  {"event_type":"slack-task","client_payload":{"title":"手動テスト","type":"task","priority":"2","description":"dispatch 経路テスト","raw_text":"...","channel_id":"","correlation_id":"manual-1","user":"tester"}}
  JSON
  ```
- **Worker ローカル E2E**: `cd workers/beads-slack && npm run dev`（`.dev.vars` にシークレット設定）→ HMAC を計算して curl POST。

## 関連

- beads 導入設計: `docs/beads-task-management-design.md`
- bd の CI 認証（dolt creds JWK）の設定手順: PR #36 の本文
- Daily Build 自動起票の実装例: `.github/workflows/daily-build-triage.yml` の `create_beads_issue` ジョブ
