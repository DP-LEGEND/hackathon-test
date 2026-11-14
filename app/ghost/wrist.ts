// One swing's forearm-sensor series from services/wrist (`wrist_series.json`): the roll angle
// and the forearm's turn rate around contact. This file only checks the JSON; every number was
// measured in Python (services/wrist/metrics.py, tempo.py). The format is in
// services/wrist/README.md; the swing's own `wrist` entry is in docs/interfaces.md.

export type WristSample = { t: number; value: number };

export type WristSeries = {
  /** A synthetic recording (wrist/synth.py): the panel must say MOCK. */
  mock: boolean;
  /** The window the coach's sensor numbers are measured in, ms from contact (-150..+100). */
  windowMs: [number, number];
  /** Forearm roll in deg, 0 at the window start, every 10 ms. t is ms from contact (the sensor's impact spike). */
  roll: WristSample[];
  /** Roll over the window: the series' value at the window end, the number the coach quotes. */
  rollChangeDeg: number;
  /**
   * The forearm's total turn rate |gyro| in deg/s (smoothed over 30 ms), every 20 ms. A null value
   * is off the recording. Null when the file has no turn-rate series (older exports).
   */
  turnRate: { t: number; value: number | null }[] | null;
};

export class WristDataError extends Error {
  name = "WristDataError";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function numbers(value: unknown, where: string): number[] {
  if (!Array.isArray(value) || !value.every(isFiniteNumber)) {
    throw new WristDataError(`${where} must be a list of finite numbers`);
  }
  return value;
}

/**
 * Checks an untrusted wrist_series.json value and returns `swingId`'s series. Null when the file
 * has no usable entry for that swing: no sensor data, so no panel. Throws WristDataError.
 */
export function parseWristSeries(value: unknown, swingId: string): WristSeries | null {
  if (!isRecord(value)) throw new WristDataError("expected a JSON object");
  if (!isRecord(value.swings)) throw new WristDataError("swings must be an object keyed by swing id");
  const entry = value.swings[swingId];
  if (entry === undefined || entry === null) return null;
  const where = `swings["${swingId}"]`;
  if (!isRecord(entry)) throw new WristDataError(`${where} must be an object`);
  // An entry the sensor couldn't be trusted for (unpaired, sync off) shows nothing, like no entry.
  if (entry.usable !== true) return null;

  const t = numbers(entry.t_ms, `${where}.t_ms`);
  const deg = numbers(entry.roll_deg, `${where}.roll_deg`);
  if (t.length < 2 || t.length !== deg.length) {
    throw new WristDataError(`${where}: t_ms and roll_deg must be the same length, at least 2`);
  }
  for (let i = 1; i < t.length; i++) {
    if (t[i] <= t[i - 1]) throw new WristDataError(`${where}.t_ms must increase`);
  }
  if (!isFiniteNumber(entry.roll_change_deg)) {
    throw new WristDataError(`${where}.roll_change_deg must be a finite number`);
  }

  const window = value.window_ms;
  const windowMs: [number, number] =
    Array.isArray(window) && window.length === 2 && window.every(isFiniteNumber) && window[0] < window[1]
      ? [window[0], window[1]]
      : [-150, 100];

  let turnRate: WristSeries["turnRate"] = null;
  const grid = value.angular_speed_t_ms;
  const speeds = entry.angular_speed_dps;
  if (grid !== undefined && speeds !== undefined) {
    const gridMs = numbers(grid, "angular_speed_t_ms");
    if (!Array.isArray(speeds) || speeds.length !== gridMs.length || !speeds.every((s) => s === null || isFiniteNumber(s))) {
      throw new WristDataError(`${where}.angular_speed_dps must match angular_speed_t_ms, numbers or null`);
    }
    turnRate = gridMs.map((ms, i) => ({ t: ms, value: speeds[i] as number | null }));
  }

  return {
    mock: value.mock === true || entry.mock === true,
    windowMs,
    roll: t.map((ms, i) => ({ t: ms, value: deg[i] })),
    rollChangeDeg: entry.roll_change_deg,
    turnRate,
  };
}

/** The sample at exactly `t` ms, or null. A read of the file, not a measurement. */
export function sampleAt(samples: { t: number; value: number | null }[] | null, t: number): number | null {
  return samples?.find((s) => s.t === t)?.value ?? null;
}
