/**
 * Slack v0 signature verification.
 *
 * basestring = `v0:${timestamp}:${rawBody}`
 * expected   = "v0:" + hex(HMAC-SHA256(signing_secret, basestring))
 *
 * `rawBody` must be the exact bytes received (before any URL-decoding), because
 * signature is computed over the wire form. `nowSeconds` is injected so the
 * timestamp window is deterministic in tests.
 */

const FIVE_MINUTES = 60 * 5;

export interface VerifyResult {
  ok: boolean;
  reason?: string;
}

export async function verifySlackSignature(
  signingSecret: string,
  timestamp: string,
  signature: string,
  rawBody: string,
  nowSeconds: number,
): Promise<VerifyResult> {
  if (!timestamp || !signature) {
    return { ok: false, reason: "missing signature headers" };
  }

  const ts = Number(timestamp);
  if (!Number.isFinite(ts)) {
    return { ok: false, reason: "invalid timestamp" };
  }

  if (Math.abs(nowSeconds - ts) > FIVE_MINUTES) {
    return { ok: false, reason: "timestamp out of range" };
  }

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(signingSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );

  const expected = "v0:" + (await hmacHex(key, `v0:${timestamp}:${rawBody}`));

  if (!timingSafeEqualHex(expected, signature)) {
    return { ok: false, reason: "signature mismatch" };
  }
  return { ok: true };
}

async function hmacHex(key: CryptoKey, message: string): Promise<string> {
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return bufferToHex(sig);
}

function bufferToHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time hexadecimal string comparison. */
function timingSafeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
