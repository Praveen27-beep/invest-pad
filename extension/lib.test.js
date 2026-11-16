import assert from "node:assert/strict";
import { test } from "node:test";
import { flush, makeCapture, normaliseServer } from "./lib.js";

const item = (n) => ({ client_id: `capture-${n}` });

test("flush sends in order and empties the queue", async () => {
  const seen = [];
  const result = await flush([item(1), item(2)], async (c) => { seen.push(c.client_id); return 201; });
  assert.deepEqual(seen, ["capture-1", "capture-2"]);
  assert.deepEqual(result, { remaining: [], sent: 2, dropped: [], stopped: null });
});

test("offline keeps everything, in order, for later", async () => {
  const queue = [item(1), item(2)];
  const result = await flush(queue, async () => { throw new TypeError("Failed to fetch"); });
  assert.deepEqual(result.remaining, queue);
  assert.equal(result.stopped, "offline");
  assert.equal(result.sent, 0);
});

test("a rejected token stops at once and loses nothing", async () => {
  const result = await flush([item(1), item(2)], async () => 401);
  assert.equal(result.stopped, "token");
  assert.equal(result.remaining.length, 2);
});

test("a server error stops and keeps the rest", async () => {
  let calls = 0;
  const result = await flush([item(1), item(2), item(3)], async () => (++calls === 1 ? 201 : 503));
  assert.equal(result.sent, 1);
  assert.equal(result.stopped, "busy");
  assert.deepEqual(result.remaining.map((c) => c.client_id), ["capture-2", "capture-3"]);
});

test("one invalid capture is set aside and does not block the others", async () => {
  const result = await flush([item(1), item(2)], async (c) => (c.client_id === "capture-1" ? 422 : 201));
  assert.equal(result.sent, 1);
  assert.deepEqual(result.dropped, [item(1)]);
  assert.deepEqual(result.remaining, []);
});

test("flush does not change the queue it was given", async () => {
  const queue = [item(1)];
  await flush(queue, async () => 201);
  assert.equal(queue.length, 1);
});

test("makeCapture trims, limits and timestamps", () => {
  const capture = makeCapture({
    kind: "question", body: "  Why?  ", id: "abc12345", now: Date.UTC(2026, 10, 16, 6, 0, 0), subjectId: "",
    context: { selection: "s".repeat(30000), url: "https://example.com", title: "T" },
  });
  assert.equal(capture.body, "Why?");
  assert.equal(capture.selection.length, 20000);
  assert.equal(capture.captured_at, "2026-11-16T06:00:00.000Z");
  assert.equal(capture.subject_id, null);
  assert.equal(makeCapture({ kind: "note", body: "x", id: "i", now: 0 }).url, "");
});

test("normaliseServer", () => {
  assert.equal(normaliseServer(" localhost:3000/ "), "http://localhost:3000");
  assert.equal(normaliseServer("https://pad.example.com/app/"), "https://pad.example.com");
  assert.equal(normaliseServer("pad.example.com"), "https://pad.example.com");
  assert.equal(normaliseServer(""), null);
  assert.equal(normaliseServer("http://"), null);
});
