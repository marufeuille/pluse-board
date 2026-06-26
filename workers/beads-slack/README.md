# beads-slack (Cloudflare Worker)

Receives the Slack `/task` slash command, verifies the Slack signature, structures
the message via GPT, and sends a `repository_dispatch` (`event_type: slack-task`)
to `pluse-board`. The `slack-beads-create` workflow then creates a beads issue and
posts the result back to Slack.

See `docs/slack-integration-design.md` (repo root) for the full architecture and
deployment checklist.

## Local development

```bash
npm install
cp .dev.vars.example .dev.vars   # fill in SLACK_SIGNING_SECRET / OPENAI_API_KEY / GH_TOKEN
npm run test                      # unit tests (signature verification)
npm run typecheck
npm run dev                       # wrangler dev (local Worker on http://localhost:8787)
```

## Deploy

```bash
npx wrangler secret put SLACK_SIGNING_SECRET
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put GH_TOKEN
npm run deploy
```

## Secrets / vars

| Name | Kind | Purpose |
|---|---|---|
| `SLACK_SIGNING_SECRET` | secret | HMAC verification of Slack requests |
| `OPENAI_API_KEY` | secret | GPT structured-output call |
| `GH_TOKEN` | secret | fine-grained PAT (or classic `repo` scope) for `repository_dispatch` |
| `REPO` | var | `marufeuille/pluse-board` (in `wrangler.toml`) |
