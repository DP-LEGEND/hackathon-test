// Compare and coach files for the /ghost replay: validation only, no maths.
// Code measures, the browser only shows: every number here is read from a file that
// services/physics/compare.py or services/coach/agent.py wrote. Nothing is recomputed.

import type { Vec3 } from "@/lib/ghost/types";
import { hipCentreAtContact, hittingWristAtContact, loadSwing, type LoadedSwing, type SwingCoordinates } from "./swing";

export type BallOutcome = "in" | "tin" | "out" | "down";

/** One PREDICTED ball path in court coordinates (metres, x across, y up, z back from the front wall). */
export type BallPath = {
  points: Vec3[];
  speedKmh: number;
  outcome: BallOutcome;
  /** Wall and floor hits, in order. */
  bounces: Vec3[];
  /** [x, z] of the first floor bounce after the front wall, or null if it never lands. */
  landing: [number, number] | null;
  frontWallHeightM: number | null;
};

export type RacketSpeed = { value: number; unit: string; label: string };

export type CompareSide = {
  swing: LoadedSwing;
  ball: BallPath;
  racketSpeed: RacketSpeed;
};

export type Change = { you: number | null; ghost: number | null; change: number | null };
export type MetricChange = Change & { key: string; unit: string };

export type CompareResult = {
  fix: { id: string; amount: number; unit: string };
  hand: "R" | "L";
  /** True when the ghost is the swing with a real fix applied (physics/ghost.py), not a copy. */
  ghostIsReal: boolean;
  you: CompareSide;
  ghost: CompareSide;
  metrics: MetricChange[];
  ball: {
    outcome: { you: BallOutcome; ghost: BallOutcome };
    speedKmh: Change;
    frontWallHeightM: Change;
    landingDepthM: Change;
  };
  assumptions: { contactSpot: Vec3; note: string };
  /** Top-level `coordinateSystem`: "court" when physics returned the swings already in court coordinates. */
  coordinateSystem: string | null;
};

/**
 * How to draw this compare's swings. With "coordinateSystem": "court" they're drawn exactly as
 * given. Otherwise they're hip-centred pipeline skeletons that the scene turns and places, with
 * the hitting wrist over the ball's start when the ball paths are shown (`withBall`).
 */
export function swingCoordinates(compare: CompareResult, withBall: boolean): SwingCoordinates {
  if (compare.coordinateSystem === "court") {
    return { system: "court", youHips: hipCentreAtContact(compare.you.swing) };
  }
  return { system: "hip-centred", youWrist: withBall ? hittingWristAtContact(compare.you.swing, compare.hand) : null };
}

export type CoachFault = {
  id: string;
  label: string;
  confidence: string;
  fix: string;
  ghostReady: boolean;
  /** What code measured, and where the fault starts. Null if the file leaves it out. */
  value: number | null;
  threshold: number | null;
  unit: string;
  severity: number | null;
  /** How far the ghost should move it (fault library `fix_amount`). */
  fixAmount: number | null;
  /** Where the fault's threshold comes from, e.g. "mock wrist-sensor swings". Null if not given. */
  source: string | null;
};

/**
 * What the coach read from the forearm sensor (its `metrics`, docs/interfaces.md swing["wrist"]).
 * `source` is null when it didn't use one, and then `skipped` says why.
 */
export type CoachWristSensor = {
  source: "sensor" | "mock sensor" | null;
  skipped: string | null;
  /** forearm_roll_deg: size of the roll through contact, deg. */
  rollDeg: number | null;
  /** forearm_roll_rate_dps: fastest roll rate about the forearm, deg/s. */
  rollRateDps: number | null;
};

/** Output of `coach.agent.coach_swing`: the top fault and its cue, decided by the fault library. */
export type CoachCaption = {
  stroke: string;
  fault: CoachFault | null;
  cue: string;
  /**
   * Faults that fired, worst first: `faults` when the file has it (saved samples), else
   * the top fault and the ghost's fault (the live coach returns only those).
   */
  faults: CoachFault[];
  /** Which fix the ghost starts on and by how much (coach #28). Null in older coach files. */
  ghostFix: string | null;
  ghostFixAmount: number | null;
  /** Why the ghost shows a different fix from the caption's, e.g. the top one isn't animated yet. */
  ghostNote: string | null;
  /** Ids of every fault that fired: `faults`, plus the top fault and the live coach's `other_faults`. */
  firedFaultIds: string[];
  wristSensor: CoachWristSensor;
};

/** True when both PREDICTED paths are the same points: the fix didn't change the ball. Equality only. */
export function sameBallPath(a: BallPath, b: BallPath): boolean {
  return (
    a.points.length === b.points.length &&
    a.points.every((p, i) => p[0] === b.points[i][0] && p[1] === b.points[i][1] && p[2] === b.points[i][2])
  );
}

export class CompareDataError extends Error {
  name = "CompareDataError";
}

const OUTCOMES: readonly BallOutcome[] = ["in", "tin", "out", "down"];

const FIX_NAMES: Record<string, string> = {
  straighten_elbow: "Straighten elbow",
  turn_shoulders_more: "Turn shoulders more",
  hold_wrist_cock: "Hold wrist cock",
  bend_elbow: "Bend elbow",
  close_stance: "Close stance",
  turn_shoulders_less: "Turn shoulders less",
  firm_wrist: "Firm wrist",
};

const METRIC_NAMES: Record<string, string> = {
  elbow_at_contact_deg: "Elbow at contact",
  shoulder_turn_deg: "Shoulder turn",
  wrist_at_contact_deg: "Wrist angle at contact",
  wrist_release_ms: "Wrist release before contact",
  stance_open_deg: "Stance open to the shot",
};

function humanise(id: string): string {
  const words = id.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function fixName(id: string): string {
  return FIX_NAMES[id] ?? humanise(id);
}

export function metricName(key: string): string {
  return METRIC_NAMES[key] ?? humanise(key);
}

/** "deg" shows as °, other units after a space. Formatting only: the value is the file's. */
export function formatValue(value: number | null, unit: string): string {
  if (value === null) return "n/a";
  return unit === "deg" ? `${value}°` : unit ? `${value} ${unit}` : String(value);
}

/** A change from the file with its sign, e.g. "+12 ms". Null when the file has none. */
export function formatChange(value: number | null, unit: string): string {
  if (value === null) return "n/a";
  if (value === 0) return "no change";
  return `${value > 0 ? "+" : ""}${formatValue(value, unit)}`;
}

export const OUTCOME_WORDS: Record<BallOutcome, string> = {
  in: "in",
  tin: "hits the tin",
  out: "out",
  down: "floor first",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function record(value: unknown, where: string): Record<string, unknown> {
  if (!isRecord(value)) throw new CompareDataError(`${where} must be an object`);
  return value;
}

function text(value: unknown, where: string): string {
  if (typeof value !== "string" || value === "") throw new CompareDataError(`${where} must be a non-empty string`);
  return value;
}

function num(value: unknown, where: string): number {
  if (!isFiniteNumber(value)) throw new CompareDataError(`${where} must be a finite number`);
  return value;
}

function numOrNull(value: unknown, where: string): number | null {
  return value === null || value === undefined ? null : num(value, where);
}

function vec3(value: unknown, where: string): Vec3 {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(isFiniteNumber)) {
    throw new CompareDataError(`${where} must be [x, y, z]`);
  }
  return [value[0], value[1], value[2]];
}

function outcome(value: unknown, where: string): BallOutcome {
  const found = OUTCOMES.find((o) => o === value);
  if (!found) throw new CompareDataError(`${where} must be one of ${OUTCOMES.join(", ")}`);
  return found;
}

function change(value: unknown, where: string): Change {
  const c = record(value, where);
  return {
    you: numOrNull(c.you, `${where}.you`),
    ghost: numOrNull(c.ghost, `${where}.ghost`),
    change: numOrNull(c.change, `${where}.change`),
  };
}

function parseBall(value: unknown, where: string): BallPath {
  const b = record(value, where);
  // Hard rule: there is no real ball, so a path that isn't marked PREDICTED is refused.
  if (b.predicted !== true || b.label !== "PREDICTED") {
    throw new CompareDataError(`${where} is not marked PREDICTED`);
  }
  if (!Array.isArray(b.points) || b.points.length < 2) {
    throw new CompareDataError(`${where}.points must hold at least two points`);
  }
  const events = Array.isArray(b.events) ? b.events : [];
  let landing: [number, number] | null = null;
  if (b.landing !== null && b.landing !== undefined) {
    if (!Array.isArray(b.landing) || b.landing.length !== 2 || !b.landing.every(isFiniteNumber)) {
      throw new CompareDataError(`${where}.landing must be [x, z] or null`);
    }
    landing = [b.landing[0], b.landing[1]];
  }
  return {
    points: b.points.map((p: unknown, i: number) => vec3(p, `${where}.points[${i}]`)),
    speedKmh: num(b.speedKmh, `${where}.speedKmh`),
    outcome: outcome(b.outcome, `${where}.outcome`),
    bounces: events.map((e: unknown, i: number) => vec3(record(e, `${where}.events[${i}]`).point, `${where}.events[${i}].point`)),
    landing,
    frontWallHeightM: numOrNull(b.frontWallHeightM, `${where}.frontWallHeightM`),
  };
}

function parseSide(value: unknown, where: string, contactFrame: number): CompareSide {
  const s = record(value, where);
  const r = record(s.racketSpeed, `${where}.racketSpeed`);
  let swing: LoadedSwing;
  try {
    // The swing's own contactFrame wins; the compare file's top-level one is the fallback.
    swing = loadSwing(s.swing, contactFrame);
  } catch (error) {
    throw new CompareDataError(`${where}.swing: ${error instanceof Error ? error.message : String(error)}`);
  }
  return {
    swing,
    ball: parseBall(s.ball, `${where}.ball`),
    racketSpeed: {
      value: num(r.value, `${where}.racketSpeed.value`),
      unit: text(r.unit, `${where}.racketSpeed.unit`),
      label: typeof r.label === "string" ? r.label : "ESTIMATE",
    },
  };
}

/** Checks an untrusted `physics.compare` JSON value. Throws CompareDataError. */
export function parseCompare(value: unknown): CompareResult {
  const c = record(value, "file");
  const fix = record(c.fix, "fix");
  const contactFrame = isFiniteNumber(c.contactFrame) && Number.isInteger(c.contactFrame) ? c.contactFrame : -1;
  const hand = c.hand === "L" ? "L" : c.hand === "R" ? "R" : null;
  if (!hand) throw new CompareDataError("hand must be R or L");

  const you = parseSide(c.you, "you", contactFrame);
  const ghost = parseSide(c.ghost, "ghost", contactFrame);
  const rawGhost = record(record(c.ghost, "ghost").swing, "ghost.swing");
  const ghostIsReal = rawGhost.synthetic === true && Array.isArray(rawGhost.edits) && rawGhost.edits.length > 0;

  const delta = record(c.delta, "delta");
  const metrics = Object.entries(record(delta.metrics, "delta.metrics")).map(([key, m]): MetricChange => {
    const row = record(m, `delta.metrics.${key}`);
    return { key, unit: typeof row.unit === "string" ? row.unit : "", ...change(row, `delta.metrics.${key}`) };
  });
  const ball = record(delta.ball, "delta.ball");
  const outcomes = record(ball.outcome, "delta.ball.outcome");
  const assumptions = record(c.assumptions, "assumptions");

  return {
    fix: { id: text(fix.id, "fix.id"), amount: num(fix.amount, "fix.amount"), unit: text(fix.unit, "fix.unit") },
    hand,
    coordinateSystem: typeof c.coordinateSystem === "string" ? c.coordinateSystem : null,
    ghostIsReal,
    you,
    ghost,
    metrics,
    ball: {
      outcome: { you: outcome(outcomes.you, "delta.ball.outcome.you"), ghost: outcome(outcomes.ghost, "delta.ball.outcome.ghost") },
      speedKmh: change(ball.speedKmh, "delta.ball.speedKmh"),
      frontWallHeightM: change(ball.frontWallHeightM, "delta.ball.frontWallHeightM"),
      landingDepthM: change(ball.landingDepthM, "delta.ball.landingDepthM"),
    },
    assumptions: {
      contactSpot: vec3(assumptions.contactSpot, "assumptions.contactSpot"),
      note: typeof assumptions.note === "string" ? assumptions.note : "",
    },
  };
}

/** One fix a sample swing can show, from public/swings/catalogue.json. */
export type CatalogueFix = {
  amount: number;
  /** The coach found the fault this fixes on this swing (else a demo size). */
  flagged: boolean;
  /** Compare file name, or null when physics couldn't apply the fix. */
  file: string | null;
  /** Why physics couldn't apply it. */
  error: string | null;
};

export type CatalogueSwing = {
  id: string;
  label: string;
  swing: string;
  coach: string;
  fixes: Record<string, CatalogueFix>;
  /** Optional wrist_series.json (services/wrist) holding this swing's forearm-sensor series. */
  wristSeries: string | null;
};

/** public/swings/catalogue.json: the saved samples plus the fix list and demo sizes. */
export type Catalogue = {
  /** physics.ghost.FIXES, in its order. */
  fixes: string[];
  units: Record<string, string>;
  /** Fix sizes for fixes the coach didn't flag (and when the coach can't be reached). */
  demoAmounts: Record<string, number>;
  swings: CatalogueSwing[];
  /** Id of the swing the demo opens on, if set. */
  defaultSwing: string | null;
};

/** A plain file name in public/swings, never a path or URL. */
function fileName(value: unknown, where: string): string {
  const name = text(value, where);
  if (!/^[\w.-]+\.json$/.test(name)) throw new CompareDataError(`${where} must be a .json file name`);
  return name;
}

function numberMap(value: unknown, where: string): Record<string, number> {
  return Object.fromEntries(Object.entries(record(value, where)).map(([k, v]) => [k, num(v, `${where}.${k}`)]));
}

/** Checks an untrusted catalogue JSON value. Throws CompareDataError. */
export function parseCatalogue(value: unknown): Catalogue {
  const c = record(value, "file");
  if (!Array.isArray(c.fixes) || !Array.isArray(c.swings)) throw new CompareDataError("fixes and swings must be lists");
  const fixes = c.fixes.map((f: unknown, i: number) => text(f, `fixes[${i}]`));
  const units = Object.fromEntries(Object.entries(record(c.units, "units")).map(([k, v]) => [k, text(v, `units.${k}`)]));
  return {
    fixes,
    units,
    defaultSwing: typeof c.defaultSwing === "string" && c.defaultSwing !== "" ? c.defaultSwing : null,
    demoAmounts: numberMap(c.demoAmounts, "demoAmounts"),
    swings: c.swings.map((s: unknown, i: number): CatalogueSwing => {
      const where = `swings[${i}]`;
      const entry = record(s, where);
      const swingFixes = Object.entries(record(entry.fixes, `${where}.fixes`)).map(([id, f]): [string, CatalogueFix] => {
        const fix = record(f, `${where}.fixes.${id}`);
        return [
          id,
          {
            amount: num(fix.amount, `${where}.fixes.${id}.amount`),
            flagged: fix.flagged === true,
            file: fix.file === undefined ? null : fileName(fix.file, `${where}.fixes.${id}.file`),
            error: typeof fix.error === "string" ? fix.error : null,
          },
        ];
      });
      return {
        id: text(entry.id, `${where}.id`),
        label: text(entry.label, `${where}.label`),
        swing: fileName(entry.swing, `${where}.swing`),
        coach: fileName(entry.coach, `${where}.coach`),
        fixes: Object.fromEntries(swingFixes),
        wristSeries:
          entry.wristSeries === undefined || entry.wristSeries === null
            ? null
            : fileName(entry.wristSeries, `${where}.wristSeries`),
      };
    }),
  };
}

function parseFault(value: unknown, where: string): CoachFault {
  const f = record(value, where);
  return {
    id: text(f.id, `${where}.id`),
    label: text(f.label, `${where}.label`),
    confidence: typeof f.confidence === "string" ? f.confidence : "unknown",
    fix: text(f.fix, `${where}.fix`),
    ghostReady: f.ghost_ready === true,
    value: numOrNull(f.value, `${where}.value`),
    threshold: numOrNull(f.threshold, `${where}.threshold`),
    unit: typeof f.unit === "string" ? f.unit : "",
    severity: numOrNull(f.severity, `${where}.severity`),
    fixAmount: numOrNull(f.fix_amount, `${where}.fix_amount`),
    source: typeof f.source === "string" && f.source !== "" ? f.source : null,
  };
}

/** The coach's sensor readings. Optional in the file (older coach output has none): never throws. */
function parseWristSensor(metrics: unknown): CoachWristSensor {
  const m = isRecord(metrics) ? metrics : {};
  const reading = (key: string): number | null => {
    const value = m[key];
    return isFiniteNumber(value) ? value : null;
  };
  return {
    source: m.wrist_sensor === "sensor" || m.wrist_sensor === "mock sensor" ? m.wrist_sensor : null,
    skipped: typeof m.wrist_sensor_skipped === "string" && m.wrist_sensor_skipped !== "" ? m.wrist_sensor_skipped : null,
    rollDeg: reading("forearm_roll_deg"),
    rollRateDps: reading("forearm_roll_rate_dps"),
  };
}

/** Checks an untrusted coach JSON value (coach_swing output, file or live). Throws CompareDataError. */
export function parseCoach(value: unknown): CoachCaption {
  const c = record(value, "file");
  const fault = c.fault === null || c.fault === undefined ? null : parseFault(c.fault, "fault");
  const ghostFault = c.ghost_fault === null || c.ghost_fault === undefined ? null : parseFault(c.ghost_fault, "ghost_fault");
  const faults = Array.isArray(c.faults)
    ? c.faults.map((f: unknown, i: number) => parseFault(f, `faults[${i}]`))
    : [fault, ghostFault].filter((f, i, all): f is CoachFault => f !== null && all.findIndex((g) => g?.id === f.id) === i);
  return {
    stroke: typeof c.stroke === "string" ? c.stroke : "",
    fault,
    cue: text(c.cue, "cue"),
    faults,
    ghostFix: typeof c.ghost_fix === "string" && c.ghost_fix !== "" ? c.ghost_fix : null,
    ghostFixAmount: numOrNull(c.ghost_fix_amount, "ghost_fix_amount"),
    ghostNote: typeof c.ghost_note === "string" && c.ghost_note !== "" ? c.ghost_note : null,
    firedFaultIds: [
      ...new Set([
        ...faults.map((f) => f.id),
        ...(fault ? [fault.id] : []),
        ...(Array.isArray(c.other_faults) ? c.other_faults.filter((id): id is string => typeof id === "string") : []),
      ]),
    ],
    wristSensor: parseWristSensor(c.metrics),
  };
}

/**
 * The coach's cue as speech (`GET /coach/{id}/voice`, PR #60). `cue` replaces the caption's cue;
 * `audioUrl` is a recording of exactly that cue, or null.
 */
export type CoachVoice = {
  cue: string;
  audioUrl: string | null;
  /** `source === "claude"`: Claude worded the cue, and the page says so. Else it's the plain caption. */
  wordedByClaude: boolean;
};

/**
 * Only audio the service made itself plays: an inline data:audio clip, or a path on this site.
 * A path must start with exactly one "/", have no backslash (browsers read "/\host" as "//host",
 * another site) and resolve to this page's origin. Anything that doesn't parse is refused. On
 * the server there's no origin to check against, so only the inline clip passes there.
 */
function playableAudio(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (/^data:audio\/[\w.+-]+;base64,/i.test(value)) return value;
  if (typeof window === "undefined") return null;
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return null;
  try {
    const origin = window.location.origin;
    return new URL(value, origin).origin === origin ? value : null;
  } catch {
    return null;
  }
}

/** Checks an untrusted voice answer. Throws CompareDataError unless it has a usable cue. */
export function parseVoice(value: unknown): CoachVoice {
  const v = record(value, "voice");
  if (typeof v.cue !== "string" || v.cue.trim() === "") throw new CompareDataError("cue must be a non-empty string");
  return { cue: v.cue.trim(), audioUrl: playableAudio(v.audioUrl), wordedByClaude: v.source === "claude" };
}
