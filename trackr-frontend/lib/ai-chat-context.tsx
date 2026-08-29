"use client";

import { createContext, useCallback, useContext, useState } from "react";

export interface OpenChatOptions {
  /** Structured context the caller already has on screen -- e.g. the ISIN, deficit
   * and date from a NegativeHoldingNotice -- sent to the backend as the system
   * prompt's "Context" section (app/routers/assistant.py), so the assistant explains
   * THIS error instead of asking the investor to describe it themselves. */
  context?: string;
  /** If set, sent as the first user turn automatically on open, instead of waiting
   * for the investor to type something. */
  initialQuestion?: string;
}

interface AIChatState {
  isOpen: boolean;
  /** Bumped on every openChat() call, including re-opening with the same seed --
   * the panel resets its conversation on change rather than only on a seed-equality
   * check, so "Ask AI about this" always starts a fresh chat. */
  sessionId: number;
  seed: OpenChatOptions | null;
  openChat: (opts?: OpenChatOptions) => void;
  closeChat: () => void;
}

const AIChatContext = createContext<AIChatState | null>(null);

export function AIChatProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [sessionId, setSessionId] = useState(0);
  const [seed, setSeed] = useState<OpenChatOptions | null>(null);

  const openChat = useCallback((opts?: OpenChatOptions) => {
    setSeed(opts ?? null);
    setSessionId((n) => n + 1);
    setIsOpen(true);
  }, []);
  const closeChat = useCallback(() => setIsOpen(false), []);

  return (
    <AIChatContext.Provider value={{ isOpen, sessionId, seed, openChat, closeChat }}>
      {children}
    </AIChatContext.Provider>
  );
}

export function useAIChat(): AIChatState {
  const ctx = useContext(AIChatContext);
  if (!ctx) throw new Error("useAIChat must be used within AIChatProvider");
  return ctx;
}
