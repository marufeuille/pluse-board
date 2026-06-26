/**
 * Structure a free-text Slack message into a beads issue via GPT function calling.
 * Returns a fallback (raw text, type=task, priority=2) on any failure so the
 * dispatch is never blocked by an LLM outage.
 */

export type IssueType = "bug" | "task" | "feature";

export interface StructuredIssue {
  title: string;
  type: IssueType;
  priority: number;
  description: string;
}

const MODEL = "gpt-4o-mini";

const TOOL = {
  type: "function" as const,
  function: {
    name: "create_issue",
    strict: true,
    description: "Structure a user's Slack message into a beads issue.",
    parameters: {
      type: "object",
      properties: {
        title: { type: "string", description: "Concise issue title." },
        type: { type: "string", enum: ["bug", "task", "feature"] },
        priority: { type: "integer", minimum: 0, maximum: 4, description: "0=highest, 4=backlog" },
        description: { type: "string", description: "Detailed description of the issue." },
      },
      required: ["title", "type", "priority", "description"],
      additionalProperties: false,
    },
  },
};

function fallback(text: string): StructuredIssue {
  return {
    title: text.slice(0, 80) || "（空のメッセージ）",
    type: "task",
    priority: 2,
    description: `${text}\n\n[LLM 構造化失敗 — raw text]`,
  };
}

export async function structureIssue(apiKey: string, text: string): Promise<StructuredIssue> {
  try {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: MODEL,
        temperature: 0,
        tool_choice: { type: "function", function: { name: "create_issue" } },
        tools: [TOOL],
        messages: [
          {
            role: "system",
            content:
              "You structure a user's Slack message into a beads issue. " +
              "Classify the type (bug/task/feature), set a priority (0-4), and write a concise title " +
              "plus a clear description. Respond in the user's language.",
          },
          { role: "user", content: text },
        ],
      }),
    });

    if (!res.ok) {
      console.error("openai error", res.status, await res.text());
      return fallback(text);
    }

    const data = (await res.json()) as {
      choices?: Array<{
        message?: { tool_calls?: Array<{ function?: { arguments?: string } }> };
      }>;
    };
    const call = data?.choices?.[0]?.message?.tool_calls?.[0];
    if (!call?.function?.arguments) return fallback(text);

    const args = JSON.parse(call.function.arguments) as Record<string, unknown>;
    const type = args.type;
    const priority = args.priority;

    if (
      typeof args.title === "string" && args.title.trim() &&
      typeof args.description === "string" &&
      (type === "bug" || type === "task" || type === "feature") &&
      typeof priority === "number" && Number.isInteger(priority) &&
      priority >= 0 && priority <= 4
    ) {
      return {
        title: args.title,
        type,
        priority,
        description: args.description,
      };
    }
    return fallback(text);
  } catch (err) {
    console.error("openai exception", err);
    return fallback(text);
  }
}
