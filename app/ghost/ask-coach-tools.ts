// The "Ask the coach" agent's client tools (lib/integrations/voice/ask-coach.tsx). Each one returns
// the data this swing view already loaded from our service, as the screen shows it: values pass
// through formatValue, labels (ESTIMATE, PREDICTED, ...) are kept, and nothing is computed here.
// The agent may only quote numbers these tools return (services/coach/ask_agent.py).

import { checkedEverything, noFaultInWhatWasChecked, PARTIAL_CHECK_CUE, tidyLabel } from "./coach-caption";
import {
  fixName,
  formatChange,
  formatValue,
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
          measured: formatValue(fault.value, fault.unit),
          fault_starts_at: formatValue(fault.threshold, fault.unit),
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
    measured_from_the_pose: compare.metrics.map((m) => ({ name: metricName(m.key), value: formatValue(m.you, m.unit) })),
    racket_speed: {
      value: formatValue(compare.you.racketSpeed.value, compare.you.racketSpeed.unit),
      label: compare.you.racketSpeed.label,
    },
    read_a_guessed_joint: compare.notMeasured.map((n) => metricName(n.measurement)),
  };
}

export function ghostResult(compare: CompareResult, option: FixOption | null) {
  const ball = (who: "you" | "ghost") => ({
    outcome: OUTCOME_WORDS[compare.ball.outcome[who]],
    speed: formatValue(compare.ball.speedKmh[who], "km/h"),
    front_wall_height: formatValue(compare.ball.frontWallHeightM[who], "m"),
    lands_from_front_wall: formatValue(compare.ball.landingDepthM[who], "m"),
  });
  return {
    fix: fixName(compare.fix.id),
    size: formatValue(compare.fix.amount, compare.fix.unit),
    coachs_pick: option?.flagged ?? false,
    demo_size_not_a_coached_fix: option ? !option.flagged : false,
    ghost_is_your_swing_unchanged: compare.noCorrection,
    note: compare.ghostNote,
    body_changes: compare.metrics
      .filter((m) => m.change !== null && m.change !== 0)
      .map((m) => ({
        name: metricName(m.key),
        you: formatValue(m.you, m.unit),
        ghost: formatValue(m.ghost, m.unit),
        change: formatChange(m.change, m.unit),
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
