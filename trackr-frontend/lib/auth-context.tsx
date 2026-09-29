"use client";
/**
 * Compatibility re-export -- the provider now lives in `packages/trackr-core/src/`.
 * There is exactly ONE AuthProvider implementation and each app mounts it once.
 * See `api-client.ts` here for the extraction note.
 */
export { ApiError, AuthProvider, useAuth } from "@trackr/core";
