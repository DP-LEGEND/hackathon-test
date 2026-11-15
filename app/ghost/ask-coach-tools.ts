// The "Ask the coach" agent's client tools (lib/integrations/voice/ask-coach.tsx). Each one returns
// the data this swing view already loaded from our service: the file's own numbers, in digits with
// the unit in words ("157.2 degrees") so the agent says them as digits; labels (ESTIMATE,
// PREDICTED, ...) are kept, and nothing is computed here.
// The agent may only quote numbers these tools return (services/coach/ask_agent.py).

import { checkedEverything, noFaultInWhatWasChecked, PARTIAL_CHECK_CUE, tidyLabel } from "./coach-caption";
import {
  fixName,
  metricName,
  OUTCOME_WORDS,
  type CoachCaption,
  type CompareResult,
} from "./compare";
import { loadCompareFor, type FixOption, type SwingEntry } from "./sources";

export type AskCoachData = {
  entry: SwingEntry;
  caption: CoachCaption | null;
  fixes: FixOption[];
  /** The fix the ghost shows now, and its comparison when it has loaded. */
  activeFix: FixOption | null;
  compare: CompareResult | null;
};

export type AskCoachTool = (parameters: Record<string, unknown>) => Promise<unknown>;

const UNIT_WORDS: Record<string, string> = {
  deg: "degrees",
  ms: "milliseconds",
  "km/h": "kilometres per hour",
  m: "metres",
  "m/s": "metres per second",
};

/** A value as the agent should say it: the file's number in digits, the unit in words ("157.2 degrees"). */
export function say(value: number | null, unit: string): string {
  if (value === null) return "not available";
  const words = UNIT_WORDS[unit] ?? unit;
  return words ? `${value} ${words}` : String(value);
}

/** A change with its sign, e.g. "-52.6 degrees"; "no change" for zero. */
export function sayChange(value: number | null, unit: string): string {
  if (value === null) return "not available";
  if (value === 0) return "no change";
  return `${value > 0 ? "+" : ""}${say(value, unit)}`;
}

export function coachCall(caption: CoachCaption | null) {
  if (!caption) return { error: "The coach's call hasn't loaded yet." };
  const fault = caption.fault;
  return {
    stroke: caption.stroke,
    call: fault
      ? tidyLabel(fault.label)
      : checkedEverything(caption)
        ? "No fault found"
        : "No fault found in what was checked",
    cue: noFaultInWhatWasChecked(caption) ? PARTIAL_CHECK_CUE : caption.cue,
    fault: fault
      ? {
          name: tidyLabel(fault.label),
          measured: say(fault.value, fault.unit),
          fault_starts_at: say(fault.threshold, fault.unit),
          confidence: fault.confidence,
          fix: fixName(fault.fix),
          threshold_comes_from: fault.source,
        }
      : null,
    not_checked_because_a_joint_was_guessed: caption.notJudged.map((n) => metricName(n.measurement)),
    not_measured: caption.notMeasured,
  };
}

export function swingMetrics(compare: CompareResult) {
  return {
    measured_from_the_pose: compare.metrics.map((m) => ({ name: metricName(m.key), value: say(m.you, m.unit) })),
    racket_speed: {
      value: say(compare.you.racketSpeed.value, compare.you.racketSpeed.unit),
      label: compare.you.racketSpeed.label,
    },
    read_a_guessed_joint: compare.notMeasured.map((n) => metricName(n.measurement)),
  };
}

export function ghostResult(compare: CompareResult, option: FixOption | null) {
  const ball = (who: "you" | "ghost") => ({
    outcome: OUTCOME_WORDS[compare.ball.outcome[who]],
    speed: say(compare.ball.speedKmh[who], "km/h"),
    front_wall_height: say(compare.ball.frontWallHeightM[who], "m"),
    lands_from_front_wall: say(compare.ball.landingDepthM[who], "m"),
  });
  return {
    fix: fixName(compare.fix.id),
    size: say(compare.fix.amount, compare.fix.unit),
    coachs_pick: option?.flagged ?? false,
    demo_size_not_a_coached_fix: option ? !option.flagged : false,
    ghost_is_your_swing_unchanged: compare.noCorrection,
    note: compare.ghostNote,
    body_changes: compare.metrics
      .filter((m) => m.change !== null && m.change !== 0)
      .map((m) => ({
        name: metricName(m.key),
        you: say(m.you, m.unit),
        ghost: say(m.ghost, m.unit),
        change: sayChange(m.change, m.unit),
      })),
    ball_label: "PREDICTED: there is no real ball, both paths come from the ball model",
    you: ball("you"),
    ghost: ball("ghost"),
    assumptions: compare.assumptions.note,
  };
}

/** The four tools, reading the swing view's latest data through `get`. */
export function askCoachTools(get: () => AskCoachData): Record<string, AskCoachTool> {
  const compareFor = async (d: AskCoachData) =>
    d.compare ?? (d.activeFix ? await loadCompareFor(d.entry, d.activeFix, 0) : null);
  return {
    get_coach_call: async () => coachCall(get().caption),
    get_swing_metrics: async () => {
      const compare = await compareFor(get());
      return compare ? swingMetrics(compare) : { error: "This swing has no measurements loaded." };
    },
    get_ghost_result: async () => {
      const d = get();
      const compare = await compareFor(d);
      return compare ? ghostResult(compare, d.activeFix) : { error: "No ghost is available for this swing." };
    },
    simulate_fix: async ({ fix }) => {
      const d = get();
      const option = d.fixes.find((f) => f.id === fix);
      if (!option) return { error: `No such fix on this swing. Fixes: ${d.fixes.map((f) => f.id).join(", ")}` };
      if (option.unavailable) return { error: option.unavailable };
      return ghostResult(await loadCompareFor(d.entry, option, 0), option);
    },
  };
}
