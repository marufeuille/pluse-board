import { verifySlackSignature } from "./slack-verify";
import { structureIssue } from "./openai";
import { sendRepositoryDispatch, type DispatchPayload } from "./github";

export interface Env {
  SLACK_SIGNING_SECRET: string;
  OPENAI_API_KEY: string;
  GH_TOKEN: string;
  REPO: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Verify the Slack signature over the raw body BEFORE parsing.
    const rawBody = await request.text();
    const timestamp = request.headers.get("x-slack-request-timestamp") ?? "";
    const signature = request.headers.get("x-slack-signature") ?? "";

    const result = await verifySlackSignature(
      env.SLACK_SIGNING_SECRET,
      timestamp,
      signature,
      rawBody,
      Math.floor(Date.now() / 1000),
    );
    if (!result.ok) {
      return new Response("Unauthorized", { status: 401 });
    }

    const params = new URLSearchParams(rawBody);
    const command = params.get("command") ?? "";
    const text = (params.get("text") ?? "").trim();
    const channelId = params.get("channel_id") ?? "";
    const responseUrl = params.get("response_url") ?? "";
    const userId = params.get("user_id") ?? "";
    const userName = params.get("user_name") ?? "";

    if (command !== "/task") {
      return json({ text: `Unknown command: ${command}` });
    }
    if (!text) {
      return json({ text: "メッセージを入力してください。例: /task ログイン画面のバグを直して" });
    }

    // Acknowledge within Slack's 3-second limit; do the work asynchronously.
    const correlationId = crypto.randomUUID();

    ctx.waitUntil(
      (async () => {
        const issue = await structureIssue(env.OPENAI_API_KEY, text);

        const payload: DispatchPayload = {
          title: issue.title,
          type: issue.type,
          priority: String(issue.priority),
          description: issue.description,
          raw_text: text,
          channel_id: channelId,
          response_url: responseUrl || undefined,
          correlation_id: correlationId,
          user: userName || userId,
        };

        const ok = await sendRepositoryDispatch(env.GH_TOKEN, env.REPO, payload);

        // Best-effort early hint via response_url (ephemeral, valid 30 min).
        // The Actions workflow posts the authoritative "起票しました" result with the bot token.
        if (responseUrl) {
          const hint = ok
            ? `起票依頼を送信しました（${issue.type}/P${issue.priority}）: ${issue.title}`
            : "起票依頼の送信に失敗しました。GitHub 側を確認してください。";
          try {
            await fetch(responseUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ text: hint }),
            });
          } catch {
            // Ignore response_url failures; the workflow posts the authoritative result.
          }
        }
      })().catch((err) => {
        console.error("waitUntil failure", err);
      }),
    );

    return json({ text: "起票中... 完了時に通知します。" });
  },
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
