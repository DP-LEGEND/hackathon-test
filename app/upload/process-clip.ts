// Sends one clip to Dev's pipeline: POST /api/process, which the same-origin catch-all proxy
// (app/api/[...path]/route.ts) forwards to POST /process in services/pipeline/server.py.
// With a second camera angle or a wrist sensor export, the same answer comes from
// POST /api/process/multi instead (fields video_a, video_b, sensor_csv, slowdown_a, slowdown_b,
// offset_b_s). XMLHttpRequest rather than fetch, so the page can show real upload progress. The
// service answers once, after pose, coach and ghost are all saved; it doesn't report steps in between.

const PROCESS_URL = "/api/process";
const MULTI_URL = "/api/process/multi";

/** Mirrors MAX_UPLOAD_BYTES in services/pipeline/server.py, so an oversized clip fails before uploading. */
export const MAX_CLIP_BYTES = 250 * 1024 * 1024;

/** The containers server.py accepts (it checks the file name's extension). */
const CLIP_EXTENSIONS: readonly string[] = [".mov", ".mp4", ".m4v", ".avi"];

/** For the file picker: any video, plus the extensions for systems that don't type .avi or .m4v. */
export const CLIP_ACCEPT = ["video/*", ...CLIP_EXTENSIONS].join(",");

/**
 * Older proxies use 502 for both timeouts and an unreachable service. Keep the
 * elapsed-time heuristic for those versions; current proxies explicitly use 504.
 */
const PROXY_GAVE_UP_MS = 25_000;

export type Hand = "auto" | "R" | "L";
export type Stroke = "auto" | "forehand" | "backhand";
export type Slowdown = "auto" | "1" | "4" | "8";
export type ClipSettings = { hand: Hand; stroke: Stroke; slowdown: Slowdown };

/** Auto everywhere: the service works out hand, stroke and timing itself. */
export const AUTO_SETTINGS: ClipSettings = { hand: "auto", stroke: "auto", slowdown: "auto" };

/** Optional inputs beside the main clip. Either file switches the upload to /process/multi. */
export type ExtraInputs = {
  /** A second camera angle of the same swing, for measured depth. */
  secondClip: File | null;
  /** The wrist sensor's export: Sensor Logger's .zip, or a .csv. Sent as `sensor_csv` either way. */
  sensorFile: File | null;
  /** "Second clip offset (s)" as typed; empty leaves offset_b_s out. */
  offset: string;
};

export const NO_EXTRAS: ExtraInputs = { secondClip: null, sensorFile: null, offset: "" };

export function usesMulti(extras: ExtraInputs): boolean {
  return extras.secondClip !== null || extras.sensorFile !== null;
}

/** For the sensor file picker: Sensor Logger's .zip export, or a .csv. */
export const SENSOR_ACCEPT = ".zip,.csv,application/zip,text/csv";

/** Mirrors the service's 10 MiB sensor limit (/process/multi), for a .zip or a .csv alike. */
export const MAX_SENSOR_BYTES = 10 * 1024 * 1024;

/** Mirrors the service's 250 MiB limit for everything in one upload (/process/multi). */
export const MAX_UPLOAD_TOTAL_BYTES = 250 * 1024 * 1024;

export type ProcessFailure =
  /** 429: the service processes one clip at a time. */
  | { kind: "busy" }
  /** 413. */
  | { kind: "too-large"; message: string }
  /** 502 straight away: the proxy couldn't reach the Python service. */
  | { kind: "offline"; message: string }
  /** 504, or a delayed legacy 502: the service may still finish and save the swing. */
  | { kind: "proxy-timeout" }
  /** 404/405: the service that answered has no upload route (it predates PR #41). */
  | { kind: "no-route" }
  /** 404/405 from /process/multi: the service can't take a second angle or sensor file yet. */
  | { kind: "no-multi-route" }
  /** Anything else, e.g. 422 "No fully tracked swing found…" or 503 "pose model unavailable". */
  | { kind: "failed"; status: number; message: string }
  /** No answer at all from the Next.js server. */
  | { kind: "network" };

export type ProcessOutcome =
  /** `warnings`: what the service flagged about this upload, as it worded them (often none). */
  | { ok: true; swingId: string; warnings: string[] }
  | { ok: false; failure: ProcessFailure }
  /** Cancel was pressed. `uploaded`: the service already had the clip and may still finish it. */
  | { ok: false; cancelled: true; uploaded: boolean };

export type ProcessJob = { result: Promise<ProcessOutcome>; cancel: () => void };

/** Why this file can't be sent, or null. The service checks the same things. */
export function checkClip(file: File): string | null {
  const dot = file.name.lastIndexOf(".");
  const extension = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!CLIP_EXTENSIONS.includes(extension)) return `“${file.name}” isn’t a MOV, MP4, M4V or AVI video.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  if (file.size > MAX_CLIP_BYTES) {
    return `Clip too large: ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_CLIP_BYTES)}, so trim it to just the swing.`;
  }
  return null;
}

/** Why this sensor export can't be sent, or null: a .zip or .csv up to 10 MB. */
export function checkSensorFile(file: Pick<File, "name" | "size">): string | null {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".zip") && !name.endsWith(".csv")) return `“${file.name}” isn’t a ZIP or CSV file.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  if (file.size > MAX_SENSOR_BYTES) {
    return `Sensor export too large: ${formatBytes(file.size)}. The limit is ${wholeMegabytes(MAX_SENSOR_BYTES)}.`;
  }
  return null;
}

type Sized = Pick<File, "size">;

/**
 * Why everything chosen can't go in one upload, or null: the video, second angle and sensor
 * export together must be at most 250 MB. Each file is checked on its own when it's chosen.
 */
export function checkUploadTotal(
  file: Sized,
  extras: { secondClip: Sized | null; sensorFile: Sized | null },
): string | null {
  const total = file.size + (extras.secondClip?.size ?? 0) + (extras.sensorFile?.size ?? 0);
  if (total <= MAX_UPLOAD_TOTAL_BYTES) return null;
  return `Your files add up to ${formatBytes(total)}. One upload can be at most ${wholeMegabytes(MAX_UPLOAD_TOTAL_BYTES)} in total, so trim a video to just the swing or remove an optional file.`;
}

/** A limit in whole megabytes ("10 MB"), the unit formatBytes uses. */
export function wholeMegabytes(bytes: number): string {
  return `${Math.round(bytes / (1024 * 1024))} MB`;
}

/** The typed offset in seconds; null when it's empty or not a number. */
function parseOffset(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[-+]?(\d+(\.\d*)?|\.\d+)$/.test(trimmed)) return null;
  const seconds = Number(trimmed);
  return Number.isFinite(seconds) ? seconds : null;
}

/** Why the typed offset can't be sent, or null. Empty is fine: it's left out. */
export function checkOffset(text: string): string | null {
  if (text.trim() === "" || parseOffset(text) !== null) return null;
  return "Enter the offset in seconds, such as 0.5 or -1.2.";
}

function singleForm(file: File, settings: ClipSettings): FormData {
  const form = new FormData();
  form.append("file", file, file.name);
  // Auto settings are left out: the service treats a missing field as "work it out".
  if (settings.hand !== "auto") form.append("hand", settings.hand);
  if (settings.stroke !== "auto") form.append("stroke", settings.stroke);
  if (settings.slowdown !== "auto") form.append("slowdown", settings.slowdown);
  return form;
}

function multiForm(file: File, settings: ClipSettings, extras: ExtraInputs): FormData {
  const form = new FormData();
  form.append("video_a", file, file.name);
  if (extras.secondClip) form.append("video_b", extras.secondClip, extras.secondClip.name);
  if (extras.sensorFile) form.append("sensor_csv", extras.sensorFile, extras.sensorFile.name);
  // As for /process, Auto settings are left out. Both angles use the one Slowdown setting.
  if (settings.hand !== "auto") form.append("hand", settings.hand);
  if (settings.stroke !== "auto") form.append("stroke", settings.stroke);
  if (settings.slowdown !== "auto") {
    form.append("slowdown_a", settings.slowdown);
    if (extras.secondClip) form.append("slowdown_b", settings.slowdown);
  }
  const offset = extras.secondClip ? parseOffset(extras.offset) : null;
  if (offset !== null) form.append("offset_b_s", String(offset));
  return form;
}

export function processClip(
  file: File,
  settings: ClipSettings,
  on: {
    /** Fraction of the upload sent, in whole percent steps; null when the size isn't known. */
    progress: (fraction: number | null) => void;
    /** The whole clip is sent; the service is working on it now. */
    uploaded: () => void;
  },
  extras: ExtraInputs = NO_EXTRAS,
): ProcessJob {
  const multi = usesMulti(extras);
  const form = multi ? multiForm(file, settings, extras) : singleForm(file, settings);

  const xhr = new XMLHttpRequest();
  let uploadedAt: number | null = null;
  let percent = -1;

  const result = new Promise<ProcessOutcome>((resolve) => {
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        on.progress(null);
        return;
      }
      const next = Math.floor((event.loaded / event.total) * 100);
      if (next === percent) return;
      percent = next;
      on.progress(next / 100);
    };
    xhr.upload.onload = () => {
      uploadedAt = performance.now();
      on.uploaded();
    };
    xhr.onload = () => {
      const waited = uploadedAt === null ? 0 : performance.now() - uploadedAt;
      resolve(readAnswer(xhr.status, xhr.responseText, waited, multi));
    };
    xhr.onerror = () => resolve({ ok: false, failure: { kind: "network" } });
    xhr.onabort = () => resolve({ ok: false, cancelled: true, uploaded: uploadedAt !== null });
  });

  xhr.open("POST", multi ? MULTI_URL : PROCESS_URL);
  xhr.setRequestHeader("Accept", "application/json");
  xhr.send(form);
  return { result, cancel: () => xhr.abort() };
}

function readAnswer(status: number, text: string, waitedAfterUpload: number, multi: boolean): ProcessOutcome {
  const body = parseJson(text);
  if (status >= 200 && status < 300) {
    const swingId = isRecord(body) ? body.swingId : undefined;
    if (typeof swingId === "string" && swingId.trim() !== "") {
      return { ok: true, swingId, warnings: isRecord(body) ? readWarnings(body.warnings) : [] };
    }
    return failed({ kind: "failed", status, message: "The service finished but didn’t say which swing it saved." });
  }
  const message = serverMessage(body) ?? `The service answered HTTP ${status}.`;
  if (status === 429) return failed({ kind: "busy" });
  if (status === 413) return failed({ kind: "too-large", message });
  if (status === 404 || status === 405) return failed({ kind: multi ? "no-multi-route" : "no-route" });
  if (status === 504) return failed({ kind: "proxy-timeout" });
  if (status === 502) {
    return failed(waitedAfterUpload >= PROXY_GAVE_UP_MS ? { kind: "proxy-timeout" } : { kind: "offline", message });
  }
  return failed({ kind: "failed", status, message });
}

function failed(failure: ProcessFailure): ProcessOutcome {
  return { ok: false, failure };
}

/** `warnings` as a list of non-empty strings (a single string counts as one); anything else is none. */
function readWarnings(value: unknown): string[] {
  const list = typeof value === "string" ? [value] : Array.isArray(value) ? value : [];
  return list.filter((item): item is string => typeof item === "string" && item.trim() !== "").map((item) => item.trim());
}

/** FastAPI says {"detail": "..."} or a list of field errors; the proxy says {"error": "..."}. */
function serverMessage(body: unknown): string | null {
  if (!isRecord(body)) return null;
  const { detail, error } = body;
  if (typeof detail === "string" && detail.trim() !== "") return detail;
  if (Array.isArray(detail)) {
    const fields = detail.flatMap((item) => {
      if (!isRecord(item) || typeof item.msg !== "string") return [];
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : undefined;
      return [typeof field === "string" ? `${field}: ${item.msg}` : item.msg];
    });
    if (fields.length > 0) return fields.join("; ");
  }
  if (typeof error === "string" && error.trim() !== "") return error;
  return null;
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 1 MB = 1024 × 1024 bytes, the unit the service's 250 MB limit uses. */
export function formatBytes(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 100) return `${Math.round(mb)} MB`;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
