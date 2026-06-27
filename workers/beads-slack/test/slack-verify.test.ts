import { describe, expect, it } from "vitest";
import { verifySlackSignature } from "../src/slack-verify";

const SECRET = "test-signing-secret";

/** Compute a Slack v0 signature exactly as Slack would, for a fixed timestamp/body. */
async function sign(timestamp: string, body: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`v0:${timestamp}:${body}`),
  );
  const hex = Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
  return `v0:${hex}`;
}

describe("verifySlackSignature", () => {
  it("accepts a valid signature", async () => {
    const ts = "1000";
    const body = "command=%2Ftask&text=hello";
    const r = await verifySlackSignature(SECRET, ts, await sign(ts, body), body, 1000);
    expect(r.ok).toBe(true);
  });

  it("rejects a tampered body", async () => {
    const ts = "1000";
    const r = await verifySlackSignature(
      SECRET,
      ts,
      await sign(ts, "command=%2Ftask&text=hello"),
      "command=%2Ftask&text=tampered",
      1000,
    );
    expect(r.ok).toBe(false);
  });

  it("rejects a signature computed with the wrong secret", async () => {
    const ts = "1000";
    const body = "x=1";
    const key = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode("wrong-secret"),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`v0:${ts}:${body}`));
    const hex = Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
    const r = await verifySlackSignature(SECRET, ts, `v0:${hex}`, body, 1000);
    expect(r.ok).toBe(false);
  });

  it("rejects an expired timestamp (>5 min drift)", async () => {
    const ts = "1000";
    const body = "x=1";
    const r = await verifySlackSignature(SECRET, ts, await sign(ts, body), body, 1000 + 60 * 5 + 1);
    expect(r.ok).toBe(false);
  });

  it("accepts a timestamp within the 5-minute window (future)", async () => {
    const ts = "1000";
    const body = "x=1";
    const r = await verifySlackSignature(SECRET, ts, await sign(ts, body), body, 1000 + 60 * 4);
    expect(r.ok).toBe(true);
  });

  it("rejects missing headers", async () => {
    const r = await verifySlackSignature(SECRET, "", "", "x=1", 1000);
    expect(r.ok).toBe(false);
  });
});
