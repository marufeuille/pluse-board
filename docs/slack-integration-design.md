# Slack → beads 起票 設計（引き継ぎ・別セッション実装用）

## Context

beads 導入は完了済み:
- **PR-1（#34）**: `bd init` + Claude 統合 + DoltHub 同期。SSOT = DoltHub（`marufeuille/pluse-board`）。
- **PR-2（#36）**: Daily Build 失敗時の `create_beads_issue` ジョブ（`.github/workflows/daily-build-triage.yml`）。

本ドキュメントは次フェーズ **「Slack から beads にタスクを起票する経路」** の引き継ぎ設計。別セッションで実装する。

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

## 関連

- beads 導入設計: `docs/beads-task-management-design.md`
- bd の CI 認証（dolt creds JWK）の設定手順: PR #36 の本文
- Daily Build 自動起票の実装例: `.github/workflows/daily-build-triage.yml` の `create_beads_issue` ジョブ
