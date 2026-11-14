// "How this was predicted", collapsed by default: how the video became a skeleton on court and
// which inputs to the PREDICTED ball paths were measured, estimated or assumed. Every label is
// the one the compare response gives and every count comes from the swing file's own flags;
// nothing here decides a label or measures anything.

import type { ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { listWords, notJudgedReason, type CompareResult, type LaunchFact } from "./compare";
import { formatFrameRanges, MIN_VISIBILITY, percentOf, summariseGuesses, type GuessField, type GuessSummary } from "./provenance";
import type { LoadedSwing } from "./swing";

/** compare's `contactMethod` in words; anything else is shown as written. */
const CONTACT_METHODS: Record<string, string> = {
  "audio-transient": "timed by the sound of the hit",
  "provided-contact-estimate": "the pipeline's estimate, where the hitting wrist moves fastest",
  "wrist-speed-peak-estimate": "estimated by physics, where the hitting wrist moves fastest",
};

const FIELD_WORDS: Record<GuessField, string> = {
  filled: "its filled-in flags",
  visibility: `its visibility scores (below ${MIN_VISIBILITY} counts as unseen)`,
  approximatedJoints: "its list of approximated joints",
};

export function PredictionPanel({ you, compare }: { you: LoadedSwing; compare: CompareResult | null }) {
  const guesses = summariseGuesses(you.guessed);
  return (
    <details className="group rounded-xl border bg-card">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-xl p-3 text-sm font-medium outline-none select-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 sm:p-4 [&::-webkit-details-marker]:hidden">
        <ChevronRight aria-hidden className="size-4 text-muted-foreground group-open:rotate-90 motion-safe:transition-transform" />
        How this was predicted
      </summary>
      <div className="flex flex-col gap-5 px-3 pb-4 text-sm sm:px-4">
        <Part title="1. The 3D skeleton">
          <p>
            Two phones film the swing from different angles. In each video a pose model finds 33 body points, and matching
            the two views places every point in 3D: a two-camera 3D pose. With only one camera, the depth is estimated by
            the pose model instead of measured.
          </p>
          <p className="text-muted-foreground">{cameraLine(you)}</p>
        </Part>

        <Part title="2. Where you stand on court">
          {compare ? (
            <>
              <p>
                {compare.coordinateSystem === "court"
                  ? "Physics stands your skeleton on the court so that your racket head at the contact frame is over the spot on court listed below. The ghost moves by exactly the same amount, so the two bodies overlap and only the fix differs."
                  : "This file's skeletons have no place on court, so the page stands you with your hitting hand over the ball's start. That placement is for display only."}
              </p>
              <p className="text-muted-foreground">{contactLine(compare, you)}</p>
            </>
          ) : (
            <p className="text-muted-foreground">Shown once the ghost has loaded.</p>
          )}
        </Part>

        <Part title="3. What the ball model used">
          {compare ? (
            <>
              <p>
                Both ball paths are <span className="font-mono text-xs font-bold tracking-wider">PREDICTED</span> from these
                inputs; there is no real ball. Each label is the one physics gave it.
              </p>
              <FactList facts={compare.howPredicted.facts} />
              {compare.howPredicted.note && <p className="text-xs text-muted-foreground">{compare.howPredicted.note}</p>}
            </>
          ) : (
            <p className="text-muted-foreground">Shown once the ghost has loaded.</p>
          )}
        </Part>

        <Part title="4. Faded joints">
          <p>
            Faded, dashed joints were filled in: the camera couldn&apos;t see them on those frames, so the pipeline
            interpolated them from nearby frames or copied them from a neighbouring joint. They keep the skeleton whole but
            they aren&apos;t measurements. The coach skips any check that would read one, physics leaves those body
            measurements out of the ghost comparison and flags a racket or ball speed that reads one, and the page lists
            each of them with the reason instead of hiding it.
          </p>
          <GuessStats summary={guesses} />
        </Part>
      </div>
    </details>
  );
}

function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h4 className="text-xs font-semibold tracking-[0.12em] text-muted-foreground uppercase">{title}</h4>
      {children}
    </section>
  );
}

function cameraLine(you: LoadedSwing): string {
  if (you.source === "stereo") return "This swing: two cameras.";
  if (you.source === "mono") {
    return `This swing: one camera, so its depth is estimated.${you.fallbackReason ? ` Why: ${you.fallbackReason}.` : ""}`;
  }
  return "This swing's file doesn't say whether it came from two cameras or one.";
}

function contactLine(compare: CompareResult, you: LoadedSwing): string {
  const { contactFrame, contactMethod } = compare.howPredicted;
  if (contactFrame !== null && contactMethod) {
    return `Contact is frame ${contactFrame}: ${CONTACT_METHODS[contactMethod] ?? contactMethod}.`;
  }
  return you.contactSource === "file"
    ? `Contact is frame ${you.contactFrame}, as the swing file gives it.`
    : `The file gives no contact frame, so frame ${you.contactFrame}, where a wrist moves fastest, stands in for it.`;
}

function LabelBadge({ label }: { label: string | null }) {
  if (label === null) return <span className="text-xs text-muted-foreground">no label in this file</span>;
  const tone = /ASSUM/i.test(label)
    ? "border-amber-400/50 text-amber-300"
    : /MEASUR|RECORD/i.test(label)
      ? "border-foreground/40"
      : "border-border text-muted-foreground";
  return (
    <Badge variant="outline" className={cn("font-mono tracking-wide", tone)}>
      {label}
    </Badge>
  );
}

function FactList({ facts }: { facts: LaunchFact[] }) {
  if (facts.length === 0) return <p className="text-muted-foreground">This file doesn&apos;t list the ball model&apos;s inputs.</p>;
  return (
    <dl className="flex flex-col divide-y rounded-lg border">
      {facts.map((fact) => (
        <div key={fact.key} className="flex flex-col gap-1 px-3 py-2 sm:grid sm:grid-cols-[11rem_1fr_auto] sm:items-baseline sm:gap-3">
          <dt className="text-muted-foreground">{fact.name}</dt>
          <dd className="flex flex-col gap-0.5">
            <span className="tabular-nums">{fact.value}</span>
            {fact.method && <span className="text-xs text-pretty text-muted-foreground">{fact.method}</span>}
            {fact.guessed && (
              <span className="text-xs text-pretty">Not a measurement: {notJudgedReason(fact.guessed).text}.</span>
            )}
          </dd>
          <dd className="flex flex-wrap items-center gap-1.5">
            <LabelBadge label={fact.label} />
            {fact.ghostLabel && (
              <>
                <span className="text-xs text-muted-foreground">ghost</span>
                <LabelBadge label={fact.ghostLabel} />
              </>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function GuessStats({ summary }: { summary: GuessSummary }) {
  const { totalFrames, recordedFrames, fadedFrames, faded, hidden } = summary;
  const source = summary.fields.length > 0 ? ` Read from ${listWords(summary.fields.map((f) => FIELD_WORDS[f]))}.` : "";
  if (recordedFrames === 0 && fadedFrames === 0) {
    return (
      <p className="text-muted-foreground">
        This swing&apos;s file doesn&apos;t mark guessed joints frame by frame, so nothing is faded. That means unknown, not
        that every joint was seen.{source}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1.5">
      <p>
        <span className="font-medium tabular-nums">
          {fadedFrames} of {totalFrames} frames ({percentOf(fadedFrames, totalFrames)}%)
        </span>{" "}
        {fadedFrames === 1 ? "has" : "have"} at least one faded joint on this swing.
        <span className="text-muted-foreground">{source}</span>
      </p>
      {faded.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-muted-foreground">
          {faded.map((j) => (
            <li key={j.joint}>
              <span className="text-foreground">{j.words.charAt(0).toUpperCase() + j.words.slice(1)}</span>:{" "}
              {formatFrameRanges(j.ranges, totalFrames)}
            </li>
          ))}
        </ul>
      )}
      {hidden.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Also guessed, but not drawn: {listWords([...new Set(hidden.map((j) => j.words))])}.
        </p>
      )}
      {recordedFrames > 0 && recordedFrames < totalFrames && (
        <p className="text-xs text-muted-foreground">
          {totalFrames - recordedFrames} frames don&apos;t say which joints were guessed, so they count as measured here.
        </p>
      )}
      {recordedFrames === 0 && (
        <p className="text-xs text-muted-foreground">
          The file only lists joints for the whole swing, not frame by frame, so those are faded on every frame.
        </p>
      )}
    </div>
  );
}
