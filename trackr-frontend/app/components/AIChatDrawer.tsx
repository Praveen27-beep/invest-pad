"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useAuth } from "@/lib/auth-context";
import { useAIChat } from "@/lib/ai-chat-context";
import { api, ApiError } from "@/lib/api-client";
import type { AskAIResponse, ChatMessageIn } from "@/lib/api-types";
import { Badge, Icon, IconButton } from "./ds";

interface DisplayMessage extends ChatMessageIn {
  /** Set on an assistant turn that failed — rendered as an inline error rather than a
   * chat bubble, and never sent back to the API as history. */
  error?: boolean;
}

const SUGGESTIONS = [
  "Explain my XIRR gap",
  "Which holdings hurt me most?",
  "Am I overexposed to financials?",
];

/**
 * "Ask AI" — a slide-over drawer, portaled to document.body so no ancestor's transform
 * or filter can become this `fixed` panel's containing block.
 *
 * Stateless on the server: every send resends the full visible turn history, matching
 * app/routers/assistant.py's own statelessness. A fresh openChat() (bumping sessionId)
 * always starts a new conversation — this is "quick question about what's on screen",
 * not a saved thread.
 */
export function AIChatDrawer() {
  const { isOpen, sessionId, seed, closeChat } = useAIChat();
  const { investorId, token } = useAuth();
  const [mounted, setMounted] = useState(false);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setMounted(true), []);

  // A fresh session: reset the conversation, and auto-send the seed question if one
  // was given (e.g. "Ask AI about this" from a NegativeHoldingNotice).
  useEffect(() => {
    if (!isOpen) return;
    setMessages([]);
    setInput("");
    if (seed?.initialQuestion) {
      void send(seed.initialQuestion, []);
    } else {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, isOpen]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string, history: DisplayMessage[]) {
    const trimmed = text.trim();
    if (!trimmed || !investorId) return;
    const withUser: DisplayMessage[] = [...history, { role: "user", content: trimmed }];
    setMessages(withUser);
    setInput("");
    setSending(true);
    try {
      const res = await api.post<AskAIResponse>(`/investors/${investorId}/ai/chat`, {
        json: {
          messages: withUser.map(({ role, content }) => ({ role, content })),
          context: seed?.context,
        },
        token,
      });
      setMessages((cur) => [...cur, { role: "assistant", content: res.reply }]);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.status === 503
            ? "The AI assistant isn't set up yet. Ask whoever runs this Trackr+ instance to enable INSIGHT_GENERATION_ENABLED."
            : err.message
          : "Something went wrong reaching the assistant.";
      setMessages((cur) => [...cur, { role: "assistant", content: message, error: true }]);
    } finally {
      setSending(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (sending) return;
    void send(input, messages);
  }

  if (!mounted || !isOpen) return null;

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        display: "flex",
        justifyContent: "flex-end",
        background: "var(--overlay-scrim)",
        animation: "trackr-fade-in var(--duration-base) ease both",
      }}
    >
      <button
        type="button"
        aria-label="Close"
        onClick={closeChat}
        style={{ position: "absolute", inset: 0, cursor: "default", border: "none", background: "transparent" }}
      />
      <div
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          width: 420,
          maxWidth: "100%",
          height: "100%",
          background: "var(--surface)",
          borderLeft: "1px solid var(--border)",
          boxShadow: "var(--shadow-overlay)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
            padding: "18px 20px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div>
            <p
              style={{
                margin: 0,
                display: "flex",
                alignItems: "center",
                gap: 6,
                font: "var(--type-h3)",
                fontFamily: "var(--font-heading)",
                color: "var(--text-primary)",
              }}
            >
              Ask AI <Badge tone="info">beta</Badge>
            </p>
            <p style={{ margin: "2px 0 0", font: "var(--type-body-sm)", color: "var(--text-tertiary)" }}>
              Help understanding Trackr+, not investment advice.
            </p>
          </div>
          <IconButton name="close" label="Close" variant="plain" size={32} onClick={closeChat} />
        </div>

        <div
          ref={scrollRef}
          style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 12 }}
        >
          {messages.length === 0 && !sending && (
            <>
              <p style={{ margin: 0, font: "var(--type-body)", color: "var(--text-tertiary)" }}>
                Ask about an error, a number on screen, or how to do something in Trackr+.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s, [])}
                    style={{
                      border: "1px solid var(--border)",
                      background: "var(--surface)",
                      borderRadius: "var(--radius-full)",
                      padding: "5px 11px",
                      cursor: "pointer",
                      font: "var(--type-body-sm)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </>
          )}

          {messages.map((m, i) => (
            <div key={i} style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
              <div
                style={{
                  maxWidth: "85%",
                  borderRadius: "var(--radius-lg)",
                  padding: "8px 12px",
                  font: "var(--type-body)",
                  ...(m.role === "user"
                    ? { background: "var(--ink-900)", color: "var(--text-inverse)" }
                    : m.error
                      ? { background: "var(--negative-tint)", color: "var(--negative)" }
                      : { background: "var(--surface-sunken)", color: "var(--text-primary)" }),
                }}
              >
                {m.content}
              </div>
            </div>
          ))}

          {sending && (
            <div style={{ display: "flex", justifyContent: "flex-start" }}>
              <div
                style={{
                  borderRadius: "var(--radius-lg)",
                  background: "var(--surface-sunken)",
                  padding: "8px 12px",
                  font: "var(--type-body)",
                  color: "var(--text-tertiary)",
                }}
              >
                Thinking…
              </div>
            </div>
          )}
        </div>

        <form
          onSubmit={handleSubmit}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderTop: "1px solid var(--border)",
            padding: 14,
          }}
        >
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question…"
            style={{
              flex: 1,
              minWidth: 0,
              boxSizing: "border-box",
              padding: "8px 12px",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border)",
              background: "var(--surface)",
              color: "var(--text-primary)",
              font: "var(--type-body)",
              outline: "none",
            }}
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            aria-label="Send"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              height: 36,
              width: 36,
              flexShrink: 0,
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--ink-900)",
              background: "var(--ink-900)",
              color: "var(--text-inverse)",
              cursor: sending || !input.trim() ? "not-allowed" : "pointer",
              opacity: sending || !input.trim() ? 0.5 : 1,
              transition: "opacity var(--duration-base) ease",
            } as CSSProperties}
          >
            <Icon name="arrow-up" size={16} />
          </button>
        </form>
      </div>
    </div>,
    document.body
  );
}
