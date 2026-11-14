// Under the 3D view: solid = measured from video, faded and dashed = estimated because the
// camera couldn't see it. On a frame the file doesn't mark, solid only means "not marked in this
// file", never "measured": absence of a record is unknown, not a measurement.

import { percentOf, type GuessSummary } from "./provenance";

export function JointLegend({
  summary,
  marked,
}: {
  summary: GuessSummary | null;
  /** The frame on screen carries its own guessed-joint record, for every figure drawn. */
  marked: boolean;
}) {
  const unrecorded = summary ? summary.totalFrames - summary.recordedFrames : 0;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-1 text-xs text-muted-foreground">
      <span className="flex items-center gap-2">
        <span aria-hidden className="h-[3px] w-6 shrink-0 rounded-full bg-foreground/85" />
        <span>
          <span className="text-foreground">Solid</span>: {marked ? "measured from video" : "not marked in this file"}
        </span>
      </span>
      <span className="flex items-center gap-2">
        <span aria-hidden className="w-6 shrink-0 border-t-[3px] border-dashed border-foreground/35" />
        <span>
          <span className="text-foreground">Faded</span>: estimated (the camera couldn&apos;t see it)
        </span>
      </span>
      {summary && summary.recordedFrames === 0 && (
        <span>
          This swing&apos;s file doesn&apos;t mark guessed joints frame by frame
          {summary.fadedFrames === 0 ? ", so nothing is faded" : ""}.
        </span>
      )}
      {summary && summary.recordedFrames > 0 && unrecorded > 0 && (
        <span>
          {unrecorded} of {summary.totalFrames} frames ({percentOf(unrecorded, summary.totalFrames)}%) don&apos;t say which
          joints were guessed.
        </span>
      )}
    </div>
  );
}
