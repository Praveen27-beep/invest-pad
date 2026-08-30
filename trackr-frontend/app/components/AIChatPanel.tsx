"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { useAIChat } from "@/lib/ai-chat-context";
import { api, ApiError } from "@/lib/api-client";
import type { AskAIResponse, ChatMessageIn } from "@/lib/api-types";

interface DisplayMessage extends ChatMessageIn {
  /** Set on an assistant turn that failed -- rendered as an inline error instead of a
   * chat bubble, and never sent back to the API as history. */
  error?: boolean;
}

/**
 * "Ask AI" -- a slide-in drawer, portaled to document.body for the same reason
 * WizardShell is (see that component's docstring: an ancestor with backdrop-filter
 * would become this `fixed` panel's containing block otherwise).
 *
 * Stateless on the server: every send resends the full visible turn history, matching
 * app/routers/assistant.py's own statelessness. A fresh AIChatProvider.openChat() call
 * (bumping sessionId) always starts a new conversation -- no history persists across
 * closes, which keeps this simple and matches "quick question about what's on screen"
 * rather than a saved, ongoing conversation.
 */
export function AIChatPanel() {
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
    const userTurn: DisplayMessage = { role: "user", content: trimmed };
    const withUser = [...history, userTurn];
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
            ? "The AI assistant isn't set up yet -- ask whoever runs this Trackr+ instance to add a Gemini API key."
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
    <div className="fixed inset-0 z-50 flex justify-end bg-navy-900/30 backdrop-blur-[1px] animate-fade-in-up">
      <button
        type="button"
        aria-label="Close"
        onClick={closeChat}
        className="absolute inset-0 cursor-default"
      />
      <div className="relative flex h-full w-full max-w-sm flex-col bg-surface shadow-2xl sm:max-w-md">
        <div className="flex items-center justify-between border-b border-navy-100 px-5 py-4">
          <div>
            <p className="font-heading text-base text-navy-900">Ask AI</p>
            <p className="text-xs text-navy-400">Help understanding Trackr+ &mdash; not investment advice.</p>
          </div>
          <button
            type="button"
            onClick={closeChat}
            aria-label="Close"
            className="press-scale rounded-full p-1.5 text-navy-400 hover:bg-cream-200 hover:text-navy-700"
          >
            <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
              <path d="M5 5l10 10M15 5 5 15" />
            </svg>
          </button>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {messages.length === 0 && !sending && (
            <p className="text-sm text-navy-400">
              Ask about an error, a number on screen, or how to do something in Trackr+.
            </p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                  m.role === "user"
                    ? "bg-navy-700 text-cream-50"
                    : m.error
                      ? "bg-negative/10 text-negative"
                      : "bg-cream-100 text-navy-700"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-xl bg-cream-100 px-3 py-2 text-sm text-navy-400">Thinking&hellip;</div>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-navy-100 px-4 py-3">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question&hellip;"
            className="flex-1 rounded-lg border border-navy-100 bg-surface px-3 py-2 text-sm focus:border-brass-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="press-scale rounded-lg bg-navy-700 px-4 py-2 text-sm font-medium text-cream-50 transition-colors hover:bg-navy-600 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </div>,
    document.body
  );
}
