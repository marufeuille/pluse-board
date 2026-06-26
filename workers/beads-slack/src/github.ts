/**
 * Send a repository_dispatch to pluse-board, which triggers the
 * slack-beads-create workflow (event_type=slack-task).
 */

export interface DispatchPayload {
  title: string;
  type: string;
  priority: string;
  description: string;
  raw_text: string;
  channel_id: string;
  response_url?: string;
  correlation_id: string;
  user: string;
}

export async function sendRepositoryDispatch(
  token: string,
  repo: string,
  payload: DispatchPayload,
): Promise<boolean> {
  const res = await fetch(`https://api.github.com/repos/${repo}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "beads-slack-worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ event_type: "slack-task", client_payload: payload }),
  });

  if (!res.ok) {
    console.error("github dispatch error", res.status, await res.text());
    return false;
  }
  return true;
}
