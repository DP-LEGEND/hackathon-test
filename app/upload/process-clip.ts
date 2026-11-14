// Sends one clip to Dev's pipeline: POST /api/process, which the same-origin catch-all proxy
// (app/api/[...path]/route.ts) forwards to POST /process in services/pipeline/server.py.
// XMLHttpRequest rather than fetch, so the page can show real upload progress. The service
// answers once, after pose, coach and ghost are all saved; it doesn't report steps in between.

const PROCESS_URL = "/api/process";

/** Mirrors MAX_UPLOAD_BYTES in services/pipeline/server.py, so an oversized clip fails before uploading. */
export const MAX_CLIP_BYTES = 250 * 1024 * 1024;

/** The containers server.py accepts (it checks the file name's extension). */
const CLIP_EXTENSIONS: readonly string[] = [".mov", ".mp4", ".m4v", ".avi"];

/** For the file picker: any video, plus the extensions for systems that don't type .avi or .m4v. */
export const CLIP_ACCEPT = ["video/*", ...CLIP_EXTENSIONS].join(",");

/**
 * The proxy gives up 30 s after it has the whole upload and answers 502, the same status as
 * "service not running". A 502 that arrives this long after the upload finished is that timeout.
 */
const PROXY_GAVE_UP_MS = 25_000;

export type Hand = "auto" | "R" | "L";
export type Stroke = "auto" | "forehand" | "backhand";
export type Slowdown = "auto" | "1" | "4" | "8";
export type ClipSettings = { hand: Hand; stroke: Stroke; slowdown: Slowdown };

/** Auto everywhere: the service works out hand, stroke and timing itself. */
export const AUTO_SETTINGS: ClipSettings = { hand: "auto", stroke: "auto", slowdown: "auto" };

export type ProcessFailure =
  /** 429: the service processes one clip at a time. */
  | { kind: "busy" }
  /** 413. */
  | { kind: "too-large"; message: string }
  /** 502 straight away: the proxy couldn't reach the Python service. */
  | { kind: "offline"; message: string }
  /** 502 after the proxy's wait: the service may still finish and save the swing. */
  | { kind: "proxy-timeout" }
  /** Anything else, e.g. 422 "No fully tracked swing found…" or 503 "pose model unavailable". */
  | { kind: "failed"; status: number; message: string }
  /** No answer at all from the Next.js server. */
  | { kind: "network" };

export type ProcessOutcome =
  | { ok: true; swingId: string }
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

export function processClip(
  file: File,
  settings: ClipSettings,
  on: {
    /** Fraction of the upload sent, in whole percent steps; null when the size isn't known. */
    progress: (fraction: number | null) => void;
    /** The whole clip is sent; the service is working on it now. */
    uploaded: () => void;
  },
): ProcessJob {
  const form = new FormData();
  form.append("file", file, file.name);
  // Auto settings are left out: the service treats a missing field as "work it out".
  if (settings.hand !== "auto") form.append("hand", settings.hand);
  if (settings.stroke !== "auto") form.append("stroke", settings.stroke);
  if (settings.slowdown !== "auto") form.append("slowdown", settings.slowdown);

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
      resolve(readAnswer(xhr.status, xhr.responseText, waited));
    };
    xhr.onerror = () => resolve({ ok: false, failure: { kind: "network" } });
    xhr.onabort = () => resolve({ ok: false, cancelled: true, uploaded: uploadedAt !== null });
  });

  xhr.open("POST", PROCESS_URL);
  xhr.setRequestHeader("Accept", "application/json");
  xhr.send(form);
  return { result, cancel: () => xhr.abort() };
}

function readAnswer(status: number, text: string, waitedAfterUpload: number): ProcessOutcome {
  const body = parseJson(text);
  if (status >= 200 && status < 300) {
    const swingId = isRecord(body) ? body.swingId : undefined;
    if (typeof swingId === "string" && swingId.trim() !== "") return { ok: true, swingId };
    return failed({ kind: "failed", status, message: "The service finished but didn’t say which swing it saved." });
  }
  const message = serverMessage(body) ?? `The service answered HTTP ${status}.`;
  if (status === 429) return failed({ kind: "busy" });
  if (status === 413) return failed({ kind: "too-large", message });
  if (status === 502) {
    return failed(waitedAfterUpload >= PROXY_GAVE_UP_MS ? { kind: "proxy-timeout" } : { kind: "offline", message });
  }
  return failed({ kind: "failed", status, message });
}

function failed(failure: ProcessFailure): ProcessOutcome {
  return { ok: false, failure };
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
