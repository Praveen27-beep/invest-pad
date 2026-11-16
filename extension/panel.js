// The notepad. Everything you save goes into a local queue first and is then sent, so
// nothing is lost if you are offline or the server is down.

import { flush, makeCapture, normaliseServer } from "./lib.js";

const $ = (id) => document.getElementById(id);
let settings = null; // { server, token }
let context = null;  // { url, title, selection } of the page the panel was opened on

const local = (keys) => chrome.storage.local.get(keys);

// ---------------------------------------------------------------- talking to Invest-pad

function request(path, options = {}) {
  return fetch(`${settings.server}/api${path}`, {
    ...options,
    credentials: "omit", // the token is the only thing that identifies you
    headers: { authorization: `Bearer ${settings.token}`, "content-type": "application/json" },
  });
}

async function sendQueue() {
  const { queue = [] } = await local("queue");
  if (!queue.length) return showQueue(0);
  const result = await flush(queue, async (capture) =>
    (await request("/ext/captures", { method: "POST", body: JSON.stringify(capture) })).status);

  // Captures added while we were sending are kept: only remove what was actually handled.
  const handled = new Set(queue.slice(0, queue.length - result.remaining.length).map((c) => c.client_id));
  const { queue: latest = [] } = await local("queue");
  const remaining = latest.filter((c) => !handled.has(c.client_id));
  await chrome.storage.local.set({ queue: remaining });

  const why = {
    offline: "Can’t reach Invest-pad. Saved here; will send when it is back.",
    token: "Invest-pad no longer accepts this token. Disconnect and connect again; your notes are kept.",
    busy: "Invest-pad is busy. Saved here; will retry.",
  }[result.stopped];
  // One message, most important first. A reason for not sending always wins over a bare count.
  if (result.dropped.length) setStatus(`${result.dropped.length} item(s) were refused by Invest-pad and not saved.`, true);
  else if (why) setStatus(`${why} (${remaining.length} waiting.)`, true);
  else if (remaining.length) showQueue(remaining.length);
  else if (result.sent) setStatus(result.sent === 1 ? "Saved to your inbox." : `${result.sent} saved to your inbox.`);
}

async function loadSubjects() {
  let subjects;
  try {
    const response = await request("/ext/subjects");
    if (!response.ok) return;
    subjects = await response.json();
    await chrome.storage.local.set({ subjects });
  } catch {
    ({ subjects = [] } = await local("subjects")); // offline: use the last list we saw
  }
  const select = $("subject");
  const chosen = select.value;
  select.replaceChildren(new Option("Decide later", ""), ...subjects.map((s) => new Option(s.name, s.id)));
  select.value = chosen;
}

// ---------------------------------------------------------------- screen

function setStatus(text, warn = false) {
  $("status").textContent = text;
  $("status").classList.toggle("warn", warn);
}

function showQueue(count) {
  if (count) setStatus(`${count} waiting to be sent.`, true);
}

function showContext() {
  const has = Boolean(context && (context.url || context.selection));
  $("context").hidden = !has;
  if (!has) return;
  $("selection").hidden = !context.selection;
  $("selection").textContent = context.selection;
  $("page").textContent = context.title ? `${context.title} — ${context.url}` : context.url;
}

function show(connected) {
  $("setup").hidden = connected;
  $("pad").hidden = !connected;
  if (connected) $("body").focus();
}

// ---------------------------------------------------------------- actions

async function save() {
  const body = $("body").value;
  if (!body.trim()) return setStatus("Write something first.", true);
  const capture = makeCapture({
    kind: document.querySelector("input[name=kind]:checked").value,
    body, context, subjectId: $("subject").value, id: crypto.randomUUID(), now: Date.now(),
  });
  const { queue = [] } = await local("queue");
  await chrome.storage.local.set({ queue: [...queue, capture] });
  $("body").value = "";
  setStatus("Saving…");
  await sendQueue();
}

async function connect() {
  const server = normaliseServer($("server").value);
  const token = $("token").value.trim();
  const status = $("setup-status");
  if (!server || !token) return (status.textContent = "Enter the address and the token.");
  // Ask Chrome for permission to talk to this one address. Nothing else is requested.
  const origins = [`${server}/*`];
  if (!(await chrome.permissions.contains({ origins })) && !(await chrome.permissions.request({ origins }))) {
    return (status.textContent = "Permission to reach that address was not given.");
  }
  settings = { server, token };
  try {
    const response = await request("/ext/subjects");
    if (response.status === 401) throw new Error("That token was not accepted.");
    if (!response.ok) throw new Error(`Invest-pad answered with an error (${response.status}).`);
  } catch (error) {
    settings = null;
    return (status.textContent = error instanceof TypeError ? "Could not reach that address." : error.message);
  }
  await chrome.storage.local.set({ settings });
  $("token").value = "";
  show(true);
  await loadSubjects();
  await sendQueue();
}

async function disconnect() {
  await chrome.storage.local.remove(["settings", "subjects"]); // the queue of unsent notes is kept
  settings = null;
  show(false);
}

// ---------------------------------------------------------------- start

$("save").addEventListener("click", save);
$("connect").addEventListener("click", connect);
$("disconnect").addEventListener("click", disconnect);
$("drop-context").addEventListener("click", () => { context = null; showContext(); });
$("body").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") save(); });
document.querySelectorAll("input[name=kind]").forEach((radio) => radio.addEventListener("change", () => {
  $("body").placeholder = radio.value === "question" ? "What do you want to find out?" : "Write a note…";
}));
window.addEventListener("online", () => settings && sendQueue());

// The background script records the page each time the notepad is opened on it.
chrome.storage.session.onChanged.addListener((changes) => {
  if (changes.context) { context = changes.context.newValue ?? null; showContext(); }
});

({ settings = null } = await local("settings"));
({ context = null } = await chrome.storage.session.get("context"));
showContext();
show(Boolean(settings));
if (settings) { await loadSubjects(); await sendQueue(); }
