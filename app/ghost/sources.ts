// Where /ghost gets swings: Dev's local swing API (services/pipeline/server.py) when it's
// running, otherwise the saved samples in public/swings. Both give the same shapes:
// a Swing, an optional coach verdict and physics.compare output per fix.
// The browser never measures anything: compare runs in Python, here or ahead of time.

import {
  CompareDataError,
  parseCatalogue,
  parseCoach,
  parseCompare,
  type Catalogue,
  type CoachCaption,
  type CompareResult,
} from "./compare";
import { loadSwing, type LoadedSwing } from "./swing";

/** Override with NEXT_PUBLIC_GHOST_API_URL (not a secret: it's a local address). */
export const GHOST_API_URL = (process.env.NEXT_PUBLIC_GHOST_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
const SAMPLES_DIR = "/swings";
const API_LIST_TIMEOUT_MS = 2500;
const API_TIMEOUT_MS = 20000; // compare runs physics on the server

/** One fix the picker offers for a swing. */
export type FixOption = {
  id: string;
  amount: number;
  unit: string;
  /** The coach found the fault this fixes on this swing. False = a fixed demo size. */
  flagged: boolean;
  /** Saved samples only: the compare file, or why physics couldn't apply the fix. */
  file: string | null;
  unavailable: string | null;
};

export type SwingEntry = {
  /** Unique across both origins, e.g. "sample:<id>" or "api:<id>". */
  key: string;
  id: string;
  origin: "sample" | "api";
  label: string;
  /** Saved samples: file names in public/swings. */
  swingFile: string | null;
  coachFile: string | null;
  fixes: FixOption[];
};

export type ApiState =
  | { status: "checking" }
  | { status: "local-only" }
  | { status: "offline"; message: string }
  | { status: "online"; ids: string[] };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function readJson(response: Response, url: string): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new Error(`${url} isn't valid JSON. NaN or Infinity values aren't allowed.`);
  }
}

/** FastAPI errors look like {"detail": "..."}; anything else falls back to the status code. */
async function apiError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (typeof detail === "object" && detail !== null && "error" in detail) return String((detail as { error: unknown }).error);
    }
  } catch {
    // not JSON: use the status below
  }
  return `HTTP ${response.status}`;
}

async function getJson<T>(url: string, parse: (value: unknown) => T, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") throw new Error(`${url} took too long to answer.`);
    throw new Error(`Couldn't reach ${url}.`);
  }
  if (!response.ok) throw new Error(`${url} answered: ${await apiError(response)}.`);
  const json = await readJson(response, url);
  try {
    return parse(json);
  } catch (error) {
    throw new Error(`${url} doesn't match the expected format: ${errorMessage(error)}.`);
  }
}

// One promise per resource, so switching fixes or steps never refetches. `attempt` is part of
// the key: Try again bumps it for a fresh request. A failed promise is dropped from the cache.
const cache = new Map<string, Promise<unknown>>();

function cached<T>(key: string, make: () => Promise<T>): Promise<T> {
  const hit = cache.get(key);
  if (hit) return hit as Promise<T>;
  const promise = make();
  cache.set(key, promise);
  promise.catch(() => cache.delete(key));
  return promise;
}

/** The API is only tried when the page runs on this computer (or a URL is configured), so a
 * deployed page never asks the browser for access to localhost. */
function apiAllowed(): boolean {
  if (process.env.NEXT_PUBLIC_GHOST_API_URL) return true;
  return ["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname);
}

/** Resolves (never rejects) with what the swing API offers right now. */
export async function checkApi(): Promise<ApiState> {
  if (!apiAllowed()) return { status: "local-only" };
  try {
    const ids = await getJson(
      `${GHOST_API_URL}/swings`,
      (value) => {
        const list = typeof value === "object" && value !== null ? (value as { swings?: unknown }).swings : undefined;
        if (!Array.isArray(list)) throw new CompareDataError("expected {swings: [...]}");
        return list.map((s: unknown, i: number) => {
          const id = typeof s === "object" && s !== null ? (s as { id?: unknown }).id : undefined;
          if (typeof id !== "string" || id === "") throw new CompareDataError(`swings[${i}].id must be a string`);
          return id;
        });
      },
      { signal: AbortSignal.timeout(API_LIST_TIMEOUT_MS) },
    );
    return { status: "online", ids };
  } catch (error) {
    return { status: "offline", message: errorMessage(error) };
  }
}

export function loadCatalogue(attempt: number): Promise<Catalogue> {
  return cached(`catalogue:${attempt}`, () => getJson(`${SAMPLES_DIR}/catalogue.json`, parseCatalogue));
}

/** Saved samples first, then live swings from the API. Live swings get every fix at its demo size. */
export function buildEntries(catalogue: Catalogue, api: ApiState): SwingEntry[] {
  const unit = (fix: string) => catalogue.units[fix] ?? "";
  const samples = catalogue.swings.map(
    (s): SwingEntry => ({
      key: `sample:${s.id}`,
      id: s.id,
      origin: "sample",
      label: s.label,
      swingFile: s.swing,
      coachFile: s.coach,
      fixes: catalogue.fixes
        .filter((id) => id in s.fixes)
        .map((id) => ({ id, unit: unit(id), ...s.fixes[id], unavailable: s.fixes[id].error })),
    }),
  );
  const live =
    api.status === "online"
      ? api.ids.map(
          (id): SwingEntry => ({
            key: `api:${id}`,
            id,
            origin: "api",
            label: id,
            swingFile: null,
            coachFile: null,
            fixes: catalogue.fixes
              .filter((fix) => fix in catalogue.demoAmounts)
              .map((fix) => ({
                id: fix,
                amount: catalogue.demoAmounts[fix],
                unit: unit(fix),
                flagged: false,
                file: null,
                unavailable: null,
              })),
          }),
        )
      : [];
  return [...samples, ...live];
}

export function loadSwingFor(entry: SwingEntry, attempt: number): Promise<LoadedSwing> {
  return cached(`swing:${entry.key}:${attempt}`, () =>
    entry.origin === "sample" && entry.swingFile
      ? getJson(`${SAMPLES_DIR}/${entry.swingFile}`, (v) => loadSwing(v))
      : getJson(`${GHOST_API_URL}/swings/${encodeURIComponent(entry.id)}`, (v) => loadSwing(v), {
          signal: AbortSignal.timeout(API_TIMEOUT_MS),
        }),
  );
}

/** Null when nobody has coached this swing: the swing API has no coach endpoint yet. */
export function loadCoachFor(entry: SwingEntry, attempt: number): Promise<CoachCaption | null> {
  const file = entry.coachFile;
  if (!file) return Promise.resolve(null);
  return cached(`coach:${entry.key}:${attempt}`, () => getJson(`${SAMPLES_DIR}/${file}`, parseCoach));
}

export function loadCompareFor(entry: SwingEntry, fix: FixOption, attempt: number): Promise<CompareResult> {
  return cached(`compare:${entry.key}:${fix.id}:${fix.amount}:${attempt}`, async () => {
    if (fix.unavailable) throw new Error(fix.unavailable);
    const result =
      entry.origin === "sample" && fix.file
        ? await getJson(`${SAMPLES_DIR}/${fix.file}`, parseCompare)
        : await getJson(`${GHOST_API_URL}/swings/${encodeURIComponent(entry.id)}/ghost`, parseCompare, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ fix: fix.id, amount: fix.amount }),
            signal: AbortSignal.timeout(API_TIMEOUT_MS),
          });
    if (result.fix.id !== fix.id) throw new Error(`Asked for ${fix.id} but got ${result.fix.id}.`);
    return result;
  });
}
