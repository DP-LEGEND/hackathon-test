// What the fix changes, you vs ghost: body measurements and the PREDICTED ball.
// Every number is read from compare output (services/physics/compare.py). Nothing is computed here.

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import {
  OUTCOME_WORDS,
  fixName,
  formatChange,
  formatValue,
  metricName,
  notJudgedReason,
  type Change,
  type CompareResult,
  type NotJudged,
} from "./compare";

type Row = {
  key: string;
  name: string;
  you: string;
  ghost: string;
  change: string;
  changed: boolean;
  /** Why this number isn't a measurement, when the coach says it reads a guessed joint. */
  caveat?: string;
};

function changeRow(key: string, name: string, c: Change, unit: string): Row {
  return {
    key,
    name,
    you: formatValue(c.you, unit),
    ghost: formatValue(c.ghost, unit),
    change: formatChange(c.change, unit),
    changed: c.change !== null && c.change !== 0,
  };
}

export function BodyChanges({
  compare,
  flagged,
  coached,
  notJudged,
}: {
  compare: CompareResult;
  /** The coach found the fault this fix addresses. */
  flagged: boolean;
  /** False when no coach has looked at this swing. */
  coached: boolean;
  /**
   * Measurements the coach wouldn't judge because they read a guessed joint. Physics measures
   * the same names here, but doesn't check for guessed joints itself, so those rows say so.
   */
  notJudged: NotJudged[];
}) {
  const why = !coached
    ? "Demo size: no coach has looked at this swing."
    : flagged
      ? "The coach flagged this fault."
      : "Demo size: the coach didn't flag this fault.";
  const rows = compare.metrics.map((m): Row => {
    const skipped = notJudged.find((n) => n.measurement === m.key);
    const row = changeRow(m.key, metricName(m.key), m, m.unit);
    if (!skipped) return row;
    const reason = notJudgedReason(skipped.why).text;
    return { ...row, changed: false, caveat: `Not a measurement: ${reason}.` };
  });
  const guessed = rows.some((r) => r.caveat);
  return (
    <DeltaCard
      id="delta-body"
      title="What the fix changes"
      note={`${fixName(compare.fix.id)} by ${formatValue(compare.fix.amount, compare.fix.unit)}, measured by code on both skeletons${
        guessed ? ", except where a row reads a joint the camera couldn't see" : ""
      }. ${why}`}
      rows={rows}
    />
  );
}

export const SAME_PATH_MESSAGE = "This fix changes your body position, not the ball";

export function BallChanges({
  compare,
  samePath,
}: {
  compare: CompareResult;
  /** Both PREDICTED paths are the same points (compare.ts sameBallPath). */
  samePath: boolean;
}) {
  const { ball, you, ghost } = compare;
  const rows: Row[] = [
    {
      key: "outcome",
      name: "Outcome",
      you: OUTCOME_WORDS[ball.outcome.you],
      ghost: OUTCOME_WORDS[ball.outcome.ghost],
      change: ball.outcome.you === ball.outcome.ghost ? "same" : "changed",
      changed: ball.outcome.you !== ball.outcome.ghost,
    },
    changeRow("speed", "Ball speed", ball.speedKmh, "km/h"),
    changeRow("wall", "Front wall height", ball.frontWallHeightM, "m"),
    changeRow("depth", "Lands from front wall", ball.landingDepthM, "m"),
    {
      key: "racket",
      name: `Racket speed (${you.racketSpeed.label})`,
      you: formatValue(you.racketSpeed.value, you.racketSpeed.unit),
      ghost: formatValue(ghost.racketSpeed.value, ghost.racketSpeed.unit),
      change: "",
      changed: false,
    },
  ];
  const note = samePath
    ? `${SAME_PATH_MESSAGE}: both PREDICTED paths are the same. There is no real ball in this demo.`
    : "There is no real ball in this demo. Both paths come from the ball model.";
  return (
    <DeltaCard
      id="delta-ball"
      title={
        <>
          Ball
          <Badge variant="outline">PREDICTED</Badge>
        </>
      }
      note={note}
      rows={rows}
      footnote={compare.assumptions.note}
    />
  );
}

function DeltaCard({
  id,
  title,
  note,
  rows,
  footnote,
}: {
  id: string;
  title: ReactNode;
  note: string;
  rows: Row[];
  footnote?: string;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2 rounded-xl border bg-card p-3 sm:p-4">
      <div className="flex flex-col gap-0.5">
        <h3 id={id} className="flex items-center gap-2 text-sm font-medium">
          {title}
        </h3>
        <p className="text-xs text-muted-foreground">{note}</p>
      </div>
      <table className="w-full text-sm tabular-nums">
        <thead>
          <tr className="text-xs text-muted-foreground">
            <th scope="col" className="py-1 pr-2 text-left font-normal">
              Measure
            </th>
            <th scope="col" className="px-2 py-1 text-right font-normal" style={{ color: YOU_COLOUR }}>
              You
            </th>
            <th scope="col" className="px-2 py-1 text-right font-normal" style={{ color: GHOST_COLOUR }}>
              Ghost
            </th>
            <th scope="col" className="py-1 pl-2 text-right font-normal">
              Change
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className={cn("border-t align-top", !row.changed && "text-muted-foreground")}>
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                {row.name}
                {row.caveat && <span className="mt-0.5 block text-xs text-pretty">{row.caveat}</span>}
              </th>
              <td className="px-2 py-1.5 text-right" style={row.changed ? { color: YOU_COLOUR } : undefined}>
                {row.you}
              </td>
              <td className="px-2 py-1.5 text-right" style={row.changed ? { color: GHOST_COLOUR } : undefined}>
                {row.ghost}
              </td>
              <td className={cn("py-1.5 pl-2 text-right", row.changed && "text-foreground")}>{row.change}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {footnote && <p className="text-xs text-muted-foreground">{footnote}</p>}
    </section>
  );
}
