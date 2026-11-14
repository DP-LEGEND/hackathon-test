// Swing data for the /ghost replay: validation, contact alignment and pose sampling.
// Plain TypeScript with no three.js, so the scene only ever receives clean poses.
// Shapes come from lib/ghost/types.ts.

import type { Swing, SwingFrame, Vec3 } from "@/lib/ghost/types";

export const JOINT_COUNT = 33;
const NOSE = 0;
const LEFT_WRIST = 15;
const RIGHT_WRIST = 16;
const LEFT_ANKLE = 27;
const RIGHT_ANKLE = 28;
const FOOT_JOINTS = [27, 28, 29, 30, 31, 32]; // ankles, heels, toes

/** Where the contact frame came from, shown on screen so a fallback is never hidden. */
export type ContactSource = "file" | "fastest-wrist";

export type LoadedSwing = {
  swing: Swing;
  contactFrame: number;
  contactSource: ContactSource;
  /** Clip time of the contact frame, in seconds. */
  contactT: number;
  /** Lowest foot height over the whole swing, used to stand the skeleton on the floor. */
  floorY: number;
  /** True when the file was y-down (raw MediaPipe) and was turned y-up for display. */
  flippedFromYDown: boolean;
  /** The pipeline's `source` ("stereo" or "mono"), if the file says. Mono depth is estimated, not measured. */
  source: string | null;
};

/** One drawable pose. Joints are hip-centred metres, y up. */
export type SkeletonPose = {
  joints: Vec3[];
  /** [throat, tip] when the file tracks the racket, otherwise null. */
  racket: readonly [Vec3, Vec3] | null;
};

/** Shared playback clock, in seconds relative to contact (0 = contact for both swings). */
export type Timeline = {
  start: number;
  end: number;
  /** One frame of the faster clip, used as the scrub step. */
  step: number;
};

export class SwingDataError extends Error {
  name = "SwingDataError";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function readVec3(value: unknown): Vec3 | null {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(isFiniteNumber)) return null;
  return [value[0], value[1], value[2]];
}

function parseFrame(value: unknown, index: number): SwingFrame {
  const where = `frame ${index}`;
  if (!isRecord(value)) throw new SwingDataError(`${where} is not an object`);
  if (!isFiniteNumber(value.t)) throw new SwingDataError(`${where}: t must be a number of seconds`);
  const { joints } = value;
  if (!Array.isArray(joints) || joints.length !== JOINT_COUNT) {
    throw new SwingDataError(`${where}: expected ${JOINT_COUNT} joints`);
  }
  return {
    t: value.t,
    joints: joints.map((joint: unknown, j: number) => {
      const point = readVec3(joint);
      if (!point) throw new SwingDataError(`${where}, joint ${j}: expected [x, y, z] as finite numbers`);
      return point;
    }),
    racketTip: readVec3(value.racketTip),
    racketThroat: readVec3(value.racketThroat),
  };
}

/** Checks an untrusted JSON value against the Swing contract. Throws SwingDataError. */
export function parseSwing(value: unknown): Swing {
  if (!isRecord(value)) throw new SwingDataError("expected a JSON object");
  const { id, fps, contactFrame, frames } = value;
  if (typeof id !== "string" || id === "") throw new SwingDataError("id must be a non-empty string");
  if (!isFiniteNumber(fps) || fps <= 0) throw new SwingDataError("fps must be a positive number");
  if (!Array.isArray(frames) || frames.length < 2) {
    throw new SwingDataError("frames must hold at least two frames");
  }
  const parsed = frames.map((frame: unknown, i: number) => parseFrame(frame, i));
  for (let i = 1; i < parsed.length; i++) {
    if (parsed[i].t <= parsed[i - 1].t) throw new SwingDataError(`frame ${i}: t must increase`);
  }
  // -1 marks "missing or out of range"; resolveContact then falls back to the fastest wrist.
  const contact =
    typeof contactFrame === "number" && Number.isInteger(contactFrame) && contactFrame >= 0 && contactFrame < parsed.length
      ? contactFrame
      : -1;
  return { id, fps, contactFrame: contact, frames: parsed };
}

function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/**
 * Frame where either wrist moves fastest relative to the hips (joints are hip-centred).
 * Same proxy the pipeline uses when it has no measured contact.
 */
export function fastestWristFrame(frames: SwingFrame[]): number {
  let best = 1;
  let bestSpeed = -1;
  for (let i = 1; i < frames.length; i++) {
    const dt = frames[i].t - frames[i - 1].t;
    for (const wrist of [LEFT_WRIST, RIGHT_WRIST]) {
      const speed = distance(frames[i].joints[wrist], frames[i - 1].joints[wrist]) / dt;
      if (speed > bestSpeed) {
        bestSpeed = speed;
        best = i;
      }
    }
  }
  return best;
}

/** Median head-above-ankles height; negative means the file is y-down (raw MediaPipe). */
function isYDown(frames: SwingFrame[]): boolean {
  const heights = frames
    .map((f) => f.joints[NOSE][1] - (f.joints[LEFT_ANKLE][1] + f.joints[RIGHT_ANKLE][1]) / 2)
    .sort((a, b) => a - b);
  return heights[Math.floor(heights.length / 2)] < 0;
}

/** Rotate 180° about x: y-down becomes y-up and left/right stay the same. */
function flipYDown(p: Vec3 | null | undefined): Vec3 | null {
  return p ? [p[0], -p[1], -p[2]] : null;
}

/**
 * Validates a Swing JSON value and prepares it for playback. Throws SwingDataError.
 * Contact frame, in order of preference: the swing's own `contactFrame`, then
 * `fileContactFrame` (e.g. the compare file's top-level one), then the fastest wrist.
 */
export function loadSwing(value: unknown, fileContactFrame?: number): LoadedSwing {
  let swing = parseSwing(value);
  const flippedFromYDown = isYDown(swing.frames);
  if (flippedFromYDown) {
    swing = {
      ...swing,
      frames: swing.frames.map((f) => ({
        t: f.t,
        joints: f.joints.map((p) => flipYDown(p) as Vec3),
        racketTip: flipYDown(f.racketTip),
        racketThroat: flipYDown(f.racketThroat),
      })),
    };
  }
  const fallback =
    fileContactFrame !== undefined &&
    Number.isInteger(fileContactFrame) &&
    fileContactFrame >= 0 &&
    fileContactFrame < swing.frames.length
      ? fileContactFrame
      : -1;
  const fileContact = swing.contactFrame >= 0 ? swing.contactFrame : fallback;
  const fromFile = fileContact >= 0;
  const contactFrame = fromFile ? fileContact : fastestWristFrame(swing.frames);
  let floorY = Infinity;
  for (const frame of swing.frames) {
    for (const j of FOOT_JOINTS) floorY = Math.min(floorY, frame.joints[j][1]);
  }
  return {
    swing: { ...swing, contactFrame },
    contactFrame,
    contactSource: fromFile ? "file" : "fastest-wrist",
    contactT: swing.frames[contactFrame].t,
    floorY,
    flippedFromYDown,
    source: isRecord(value) && typeof value.source === "string" ? value.source : null,
  };
}

/** A timeline covering both swings, with 0 at contact for each. */
export function buildTimeline(swings: LoadedSwing[]): Timeline {
  let start = 0;
  let end = 0;
  let fastestFps = 0;
  for (const s of swings) {
    const frames = s.swing.frames;
    start = Math.min(start, frames[0].t - s.contactT);
    end = Math.max(end, frames[frames.length - 1].t - s.contactT);
    fastestFps = Math.max(fastestFps, s.swing.fps);
  }
  return { start, end, step: 1 / fastestFps };
}

/** Index of the last frame at or before clip time t (clamped). */
function frameBefore(frames: SwingFrame[], t: number): number {
  let lo = 0;
  let hi = frames.length - 1;
  if (t <= frames[0].t) return 0;
  if (t >= frames[hi].t) return hi - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t <= t) lo = mid;
    else hi = mid;
  }
  return lo;
}

function clipTime(s: LoadedSwing, tau: number): number {
  const frames = s.swing.frames;
  return Math.min(Math.max(s.contactT + tau, frames[0].t), frames[frames.length - 1].t);
}

/** Nearest source frame at timeline time tau (seconds from contact). */
export function frameIndexAt(s: LoadedSwing, tau: number): number {
  const frames = s.swing.frames;
  const t = clipTime(s, tau);
  const i = frameBefore(frames, t);
  return t - frames[i].t < frames[i + 1].t - t ? i : i + 1;
}

/**
 * Pose at timeline time tau, linearly interpolated between the two nearest frames so slow
 * motion stays smooth. Before its first or after its last frame a swing holds that pose.
 */
export function samplePose(s: LoadedSwing, tau: number): SkeletonPose {
  const frames = s.swing.frames;
  const t = clipTime(s, tau);
  const i = frameBefore(frames, t);
  const a = frames[i];
  const b = frames[i + 1];
  const alpha = Math.min(Math.max((t - a.t) / (b.t - a.t), 0), 1);
  const joints = a.joints.map((p, j): Vec3 => {
    const q = b.joints[j];
    return [p[0] + (q[0] - p[0]) * alpha, p[1] + (q[1] - p[1]) * alpha, p[2] + (q[2] - p[2]) * alpha];
  });
  const nearest = alpha < 0.5 ? a : b;
  const racket =
    nearest.racketThroat && nearest.racketTip ? ([nearest.racketThroat, nearest.racketTip] as const) : null;
  return { joints, racket };
}
