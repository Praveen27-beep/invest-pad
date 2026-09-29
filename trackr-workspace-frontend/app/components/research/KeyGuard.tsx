"use client";

import { useEffect, useRef } from "react";
import { useAuth } from "@trackr/core";
import { clearAllKeys } from "@/lib/research-agent";

/**
 * Clears every provider key held in this tab's memory when the login or the selected investor
 * changes, including logout (BE 23: "logout clears in-memory keys and invalidates active
 * context"). Keys are namespaced by login and investor anyway; clearing them outright means a
 * key typed for one identity cannot outlive it even in memory.
 */
export function KeyGuard() {
  const { user, investorId } = useAuth();
  const identity = `${user?.id ?? ""}|${investorId}`;
  const last = useRef(identity);
  useEffect(() => {
    if (last.current !== identity) {
      clearAllKeys();
      last.current = identity;
    }
  }, [identity]);
  return null;
}
