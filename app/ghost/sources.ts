// Where /ghost gets swings: Dev's local Python service through the same-origin Next.js proxy
// (app/api/[...path]/route.ts, so there's no CORS), otherwise the saved samples in
// public/swings. Both give the same shapes: a Swing, the coach's verdict and physics.compare
// output per fix. The browser never measures anything: it all runs in Python.

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
import { parseWristSeries, type WristSeries } from "./wrist";

const API = "/api"; // the proxy answers 502 when the Python service isn't running
const SAMPLES_DIR = "/swings";
const API_LIST_TIMEOUT_MS = 4000;
const API_TIMEOUT_MS = 30000; // coach and compare run physics on the server

/** One fix the picker offers for a swing. */
export type FixOption = {
  id: string;
  amount: number;
  unit: string;
  /** The coach found the fault this fixes on this swing. False = a fixed demo size. */
  flagged: boolean;
  /** Saved samples only: the compare file. */
  file: string | null;
  /** Why physics can't show this fix on this swing, or null. */
  unavailable: string | null;
};

export type LiveSwing = { id: string; /** Labelled fault from data/labels, e.g. "over_rotation". */ label: string | null };

export type SwingEntry = {
  /** Unique across both origins, e.g. "sample:<id>" or "api:<id>". */
  key: string;
  id: string;
  origin: "sample" | "api";
  label: string;
  /** Live swings: the labelled fault, if any. */
  fault: string | null;
  /** The swing the demo opens on. */
  isDefault: boolean;
  /** Saved samples: file names in public/swings. */
  swingFile: string | null;
  coachFile: string | null;
  /** Saved samples with forearm-sensor data: the wrist_series.json holding this swing. */
  wristFile: string | null;
  /** Before the coach answers. Live swings: every fix at its demo size (see fixOptionsFor). */
  fixes: FixOption[];
};

export type ApiState =
  | { status: "checking" }
  | { status: "offline"; message: string }
  | { status: "online"; swings: LiveSwing[] };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** The service says {"detail": "..."} (FastAPI) and the proxy says {"error": "..."}. */
async function apiError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null) {
      const { detail, error } = body as { detail?: unknown; error?: unknown };
      if (typeof detail === "string") return detail;
      if (typeof detail === "object" && detail !== null && "error" in detail) return String((detail as { error: unknown }).error);
      if (typeof error === "string") return error;
    }
  } catch {
    // not JSON: use the status below
  }
  return `HTTP ${response.status}`;
}

async function getJson<T>(url: string, parse: (value: unknown) => T, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store", ...init });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") throw new Error(`${url} took too long to answer.`);
    throw new Error(`Couldn't reach ${url}.`);
  }
  if (!response.ok) throw new Error(`${url} answered: ${await apiError(response)}`);
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new Error(`${url} isn't valid JSON. NaN or Infinity values aren't allowed.`);
  }
  try {
    return parse(json);
  } catch (error) {
    throw new Error(`${url} doesn't match the expected format: ${errorMessage(error)}.`);
  }
}

function postJson<T>(url: string, body: unknown, parse: (value: unknown) => T): Promise<T> {
  return getJson(url, parse, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(API_TIMEOUT_MS),
  });
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

function parseLiveSwings(value: unknown): LiveSwing[] {
  const list = typeof value === "object" && value !== null ? (value as { swings?: unknown }).swings : undefined;
  if (!Array.isArray(list)) throw new CompareDataError("expected {swings: [...]}");
  return list.map((s: unknown, i: number) => {
    const { id, label } = (typeof s === "object" && s !== null ? s : {}) as { id?: unknown; label?: unknown };
    if (typeof id !== "string" || id === "") throw new CompareDataError(`swings[${i}].id must be a string`);
    return { id, label: typeof label === "string" && label !== "" ? label : null };
  });
}

/** Resolves (never rejects) with what the live service offers right now. */
export async function checkApi(): Promise<ApiState> {
  try {
    const swings = await getJson(`${API}/swings`, parseLiveSwings, { signal: AbortSignal.timeout(API_LIST_TIMEOUT_MS) });
    return { status: "online", swings };
  } catch (error) {
    return { status: "offline", message: errorMessage(error) };
  }
}

export function loadCatalogue(attempt: number): Promise<Catalogue> {
  return cached(`catalogue:${attempt}`, () => getJson(`${SAMPLES_DIR}/catalogue.json`, parseCatalogue));
}

function words(label: string): string {
  return label.replace(/_/g, "-");
}

/** Saved samples first (the demo swing at the top), then live swings. */
const SAMPLE_KEY = "sample:";
const LIVE_KEY = "api:";

export type Selection = {
  /** The swing on screen, or null. */
  entry: SwingEntry | null;
  /** A swing was picked but its list no longer has it (and that list has finished loading). */
  gone: boolean;
};

/**
 * Which swing is on screen. Before anything is picked: the swing a link asked for
 * (/ghost?swing=<id>, how /upload opens a new swing), else the demo swing. After a pick, only
 * the swing that was picked. Never a silent switch: if it drops out of (or never shows up in)
 * its list, `entry` is null and `gone` says so. While its list is still loading (catalogue, or
 * the live list being re-checked), it isn't called gone yet.
 */
export function resolveSelection(
  entries: SwingEntry[],
  selectedKey: string | null,
  loaded: { samples: boolean; live: boolean },
  requestedId: string | null = null,
): Selection {
  if (selectedKey === null && requestedId !== null) {
    // An id alone doesn't say which list it's in. Wait for both, then prefer the live swing
    // (uploads are live), so the swing shown never changes once it's on screen.
    if (!loaded.samples || !loaded.live) return { entry: null, gone: false };
    const entry =
      entries.find((e) => e.origin === "api" && e.id === requestedId) ??
      entries.find((e) => e.id === requestedId) ??
      null;
    return { entry, gone: entry === null };
  }
  if (selectedKey === null) return { entry: entries.find((e) => e.isDefault) ?? null, gone: false };
  const entry = entries.find((e) => e.key === selectedKey) ?? null;
  // Live entries are built from the catalogue too, so a live list needs both loaded.
  const listLoaded = selectedKey.startsWith(LIVE_KEY) ? loaded.samples && loaded.live : loaded.samples;
  return { entry, gone: entry === null && listLoaded };
}

export function buildEntries(catalogue: Catalogue, api: ApiState): SwingEntry[] {
  const unit = (fix: string) => catalogue.units[fix] ?? "";
  const defaultId = catalogue.defaultSwing ?? catalogue.swings[0]?.id ?? null;
  const samples = catalogue.swings
    .map(
      (s): SwingEntry => ({
        key: `${SAMPLE_KEY}${s.id}`,
        id: s.id,
        origin: "sample",
        label: s.label,
        fault: null,
        isDefault: s.id === defaultId,
        swingFile: s.swing,
        coachFile: s.coach,
        wristFile: s.wristSeries,
        fixes: catalogue.fixes
          .filter((id) => id in s.fixes)
          .map((id) => {
            const f = s.fixes[id];
            return { id, unit: unit(id), amount: f.amount, flagged: f.flagged, file: f.file, unavailable: f.error };
          }),
      }),
    )
    .sort((a, b) => Number(b.isDefault) - Number(a.isDefault));
  const live =
    api.status === "online"
      ? api.swings.map(
          (s): SwingEntry => ({
            key: `${LIVE_KEY}${s.id}`,
            id: s.id,
            origin: "api",
            label: s.label ? `${s.id} · labelled ${words(s.label)}` : s.id,
            fault: s.label,
            isDefault: false,
            swingFile: null,
            coachFile: null,
            wristFile: null,
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

/**
 * The fixes to offer once the coach has answered. Saved samples already carry the coach's
 * sizes (their compare files were made with them). Live swings take the ghost fix's size
 * (`ghost_fix_amount`) and each flagged fault's `fix_amount`; the rest stay at demo size.
 */
export function fixOptionsFor(entry: SwingEntry, coach: CoachCaption | null): FixOption[] {
  if (entry.origin === "sample" || !coach) return entry.fixes;
  return entry.fixes.map((fix) => {
    const fault = coach.faults.find((f) => f.fix === fix.id && f.ghostReady && f.fixAmount !== null);
    const amount = fix.id === coach.ghostFix && coach.ghostFixAmount !== null ? coach.ghostFixAmount : fault?.fixAmount;
    return amount === null || amount === undefined ? fix : { ...fix, amount, flagged: true };
  });
}

/**
 * The fix the coach starts the ghost on: its ghost_fix (#28), else (older coach files) the
 * worst fault physics can fix on this swing. Null when the coach found none it can show.
 */
export function coachPickFix(fixes: FixOption[], coach: CoachCaption | null): FixOption | null {
  const usable = fixes.filter((f) => f.unavailable === null);
  const byId = (id: string | null | undefined) => usable.find((f) => f.id === id);
  return byId(coach?.ghostFix) ?? (coach?.faults ?? []).map((f) => byId(f.fix)).find((f) => f !== undefined) ?? null;
}

export function loadSwingFor(entry: SwingEntry, attempt: number): Promise<LoadedSwing> {
  return cached(`swing:${entry.key}:${attempt}`, () =>
    entry.origin === "sample" && entry.swingFile
      ? getJson(`${SAMPLES_DIR}/${entry.swingFile}`, (v) => loadSwing(v))
      : getJson(`${API}/swings/${encodeURIComponent(entry.id)}`, (v) => loadSwing(v), {
          signal: AbortSignal.timeout(API_TIMEOUT_MS),
        }),
  );
}

/**
 * The swing's forearm-sensor series (services/wrist), or null when it has none, so the Wrist
 * sensor panel stays hidden. Saved samples name a wrist_series.json in the catalogue
 * (`wristSeries`). Live swings have no source yet: the API doesn't serve wrist data.
 */
export function loadWristFor(entry: SwingEntry, attempt: number): Promise<WristSeries | null> {
  return cached(`wrist:${entry.key}:${attempt}`, async () =>
    entry.wristFile ? getJson(`${SAMPLES_DIR}/${entry.wristFile}`, (v) => parseWristSeries(v, entry.id)) : null,
  );
}

/** Saved samples: the coach file made ahead of time. Live swings: Dev's coach route. */
export function loadCoachFor(entry: SwingEntry, attempt: number): Promise<CoachCaption> {
  return cached(`coach:${entry.key}:${attempt}`, () =>
    entry.origin === "sample" && entry.coachFile
      ? getJson(`${SAMPLES_DIR}/${entry.coachFile}`, parseCoach)
      : postJson(`${API}/coach/${encodeURIComponent(entry.id)}`, {}, parseCoach),
  );
}

export function loadCompareFor(entry: SwingEntry, fix: FixOption, attempt: number): Promise<CompareResult> {
  return cached(`compare:${entry.key}:${fix.id}:${fix.amount}:${attempt}`, async () => {
    if (fix.unavailable) throw new Error(fix.unavailable);
    const result =
      entry.origin === "sample" && fix.file
        ? await getJson(`${SAMPLES_DIR}/${fix.file}`, parseCompare)
        : await postJson(`${API}/compare/${encodeURIComponent(entry.id)}`, { fix: fix.id, amount: fix.amount }, parseCompare);
    if (result.fix.id !== fix.id) throw new Error(`Asked for ${fix.id} but got ${result.fix.id}.`);
    return result;
  });
}
