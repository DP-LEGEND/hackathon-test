"use client";

import { useEffect, useState } from "react";

export type Async<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; value: T };

/**
 * Follows one promise (null = nothing to load). Pass the same promise object while the
 * request is the same (sources.ts caches them); a new promise restarts the state.
 */
export function useAsync<T>(promise: Promise<T> | null): Async<T> {
  const [settled, setSettled] = useState<{ promise: Promise<T>; result: Async<T> } | null>(null);

  useEffect(() => {
    if (!promise) return;
    let live = true;
    promise.then(
      (value) => {
        if (live) setSettled({ promise, result: { status: "ready", value } });
      },
      (error: unknown) => {
        if (live) setSettled({ promise, result: { status: "error", message: error instanceof Error ? error.message : String(error) } });
      },
    );
    return () => {
      live = false;
    };
  }, [promise]);

  if (!promise) return { status: "idle" };
  return settled?.promise === promise ? settled.result : { status: "loading" };
}
