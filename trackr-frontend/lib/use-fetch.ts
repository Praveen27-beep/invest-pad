"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api-client";

interface FetchState<T> {
  data: T | null;
  error: string | null;
  /** The raw ApiError, when the failure came from the API -- lets a caller read
   * structured fields (e.g. MissingPriceError's `isins`) that `error`'s plain string
   * loses. `error` stays a plain string for every existing caller that only prints it. */
  errorDetail: ApiError | null;
  loading: boolean;
  refetch: () => void;
}

/**
 * GET a JSON endpoint from a client component. All read endpoints this app calls take
 * investor_id in the path -- which lives in localStorage (auth-context.tsx), so there
 * is no way to resolve it in a Server Component without a cookie the backend doesn't
 * set. Client-side fetching keeps that resolution consistent across every page rather
 * than splitting the app between two data-fetching strategies.
 */
export function useFetch<T>(
  path: string | null,
  query?: Record<string, string | number | boolean | undefined | null>,
  token?: string | null
): FetchState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDetail, setErrorDetail] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setErrorDetail(null);
    api
      .get<T>(path, { query, token })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : String(err));
        setErrorDetail(err instanceof ApiError ? err : null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, JSON.stringify(query), token, tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  return { data, error, errorDetail, loading, refetch };
}
