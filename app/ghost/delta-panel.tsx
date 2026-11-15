// What the fix changes, you vs ghost: body measurements and the PREDICTED ball.
// Every number is read from compare output (services/physics/compare.py). Nothing is computed here.
// A number that reads a guessed joint says so, and what physics left out is listed, not hidden.

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
import { ReasonList } from "./reason-list";

/** compare `notMeasured` keys the Ball card flags on its own rows, so the body card doesn't list them. */
const BALL_FLAGS = new Set(["ball_speed", "racket_speed"]);

/** Physics' reason first (compare `notMeasured`), then the coach's: either means the number reads a guessed joint. */
function guessedWhy(key: string, ...lists: NotJudged[][]): string | null {
  for (const list of lists) {
    const hit = list.find((n) => n.measurement === key);
    if (hit) return hit.why;
  }
  return null;
}

/** The row, greyed out and saying why, when its number reads a guessed joint. */
function withCaveat(row: Row, why: string | null): Row {
  return why ? { ...row, changed: false, caveat: `Not a measurement: ${notJudgedReason(why).text}.` } : row;
}

/** Why the ghost is your swing unchanged: the service's ghostNote, else a plain statement. */
function noCorrectionNote(compare: CompareResult): string {
  return compare.ghostNote ?? "Physics made no correction on this swing.";
}

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
   * Measurements the coach wouldn't judge because they read a guessed joint. Physics leaves out
   * the ones it finds itself (compare `notMeasured`); a row either list names says so.
   */
  notJudged: NotJudged[];
}) {
  const why = !coached
    ? "Demo size: no coach has looked at this swing."
    : flagged
      ? "The coach flagged this fault."
      : "Demo size: the coach didn't flag this fault.";
  const rows = compare.metrics.map((m): Row =>
    withCaveat(changeRow(m.key, metricName(m.key), m, m.unit), guessedWhy(m.key, compare.notMeasured, notJudged)),
  );
  const guessed = rows.some((r) => r.caveat);
  // What physics left out because it would read a guessed joint: listed, never hidden.
  const shown = new Set(compare.metrics.map((m) => m.key));
  const leftOut = compare.notMeasured.filter((n) => !shown.has(n.measurement) && !BALL_FLAGS.has(n.measurement));
  const note = compare.noCorrection
    ? `${noCorrectionNote(compare)} The ghost is your swing unchanged.`
    : `${fixName(compare.fix.id)} by ${formatValue(compare.fix.amount, compare.fix.unit)}, measured by code on both skeletons${
        guessed ? ", except where a row reads a joint the camera couldn't see" : ""
      }. ${why}`;
  return (
    <DeltaCard
      id="delta-body"
      title="What the fix changes"
      note={note}
      rows={rows}
      after={leftOut.length > 0 ? <ReasonList label="Not measured" items={leftOut} /> : null}
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
  // Physics keeps these two numbers when they read a guessed joint, but flags them (notMeasured).
  const rows: Row[] = [
    {
      key: "outcome",
      name: "Outcome",
      you: OUTCOME_WORDS[ball.outcome.you],
      ghost: OUTCOME_WORDS[ball.outcome.ghost],
      change: ball.outcome.you === ball.outcome.ghost ? "same" : "changed",
      changed: ball.outcome.you !== ball.outcome.ghost,
    },
    withCaveat(changeRow("speed", "Ball speed", ball.speedKmh, "km/h"), guessedWhy("ball_speed", compare.notMeasured)),
    changeRow("wall", "Front wall height", ball.frontWallHeightM, "m"),
    changeRow("depth", "Lands from front wall", ball.landingDepthM, "m"),
    withCaveat(
      {
        key: "racket",
        name: `Racket speed (${you.racketSpeed.label})`,
        you: formatValue(you.racketSpeed.value, you.racketSpeed.unit),
        ghost: formatValue(ghost.racketSpeed.value, ghost.racketSpeed.unit),
        change: "",
        changed: false,
      },
      guessedWhy("racket_speed", compare.notMeasured),
    ),
  ];
  // No correction: the paths match because the ghost is your swing unchanged, not because a fix
  // moved only the body, so the same-path message would be false here.
  const note = compare.noCorrection
    ? `${noCorrectionNote(compare)} Both PREDICTED paths are the same. There is no real ball in this demo.`
    : samePath
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
  after,
  footnote,
}: {
  id: string;
  title: ReactNode;
  note: string;
  rows: Row[];
  /** Shown under the table, e.g. what physics left out. */
  after?: ReactNode;
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
      {after}
      {footnote && <p className="text-xs text-muted-foreground">{footnote}</p>}
    </section>
  );
}
