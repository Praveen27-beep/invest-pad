// The parts of the notepad that do not touch the browser, so they can be tested with Node.

export const LIMITS = { body: 20000, selection: 20000, url: 2000, title: 500 };

/** Build the record that is queued and later sent. `id` makes a retry harmless. */
export function makeCapture({ kind, body, context, subjectId, id, now }) {
  return {
    client_id: id,
    kind,
    body: body.trim().slice(0, LIMITS.body),
    selection: (context?.selection ?? "").slice(0, LIMITS.selection),
    url: (context?.url ?? "").slice(0, LIMITS.url),
    page_title: (context?.title ?? "").slice(0, LIMITS.title),
    captured_at: new Date(now).toISOString(),
    subject_id: subjectId || null,
  };
}

/** Normalise what the user typed as the Invest-pad address: "localhost:3000/" -> "http://localhost:3000". */
export function normaliseServer(input) {
  let text = input.trim();
  if (!text) return null;
  if (!/^https?:\/\//i.test(text)) text = (/^(localhost|127\.0\.0\.1)(:|\/|$)/.test(text) ? "http://" : "https://") + text;
  try {
    const url = new URL(text);
    const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
    return local || url.hostname.includes(".") ? url.origin : null;
  } catch {
    return null;
  }
}

/**
 * Try to send everything in the queue, oldest first.
 * `send(capture)` resolves to an HTTP status, or rejects if the network is down.
 *
 * Returns what is still waiting and why we stopped:
 *   sent       how many were delivered (201)
 *   dropped    captures the server refused as invalid (4xx other than 401/429) — kept out of
 *              the queue so one bad item cannot block the rest, and reported to the user
 *   stopped    null | "offline" | "token" | "busy"
 */
export async function flush(queue, send) {
  const remaining = [...queue];
  const dropped = [];
  let sent = 0;
  let stopped = null;
  while (remaining.length) {
    let status;
    try {
      status = await send(remaining[0]);
    } catch {
      stopped = "offline";
      break;
    }
    if (status === 201) sent += 1;
    else if (status === 401) { stopped = "token"; break; }
    else if (status === 429 || status >= 500) { stopped = "busy"; break; }
    else dropped.push(remaining[0]);
    remaining.shift();
  }
  return { remaining, sent, dropped, stopped };
}
