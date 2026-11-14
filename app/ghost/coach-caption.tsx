// Coach caption laid over the 3D view, like a subtitle: the top fault and its cue.
// Orange = what the player did (the fault), cyan = the fix (the cue).

import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import type { CoachCaption } from "./compare";

export type CoachState = { status: "ready"; caption: CoachCaption } | { status: "error"; message: string };

export function CoachCaptionBar({ coach }: { coach: CoachState }) {
  return (
    <div className="pointer-events-none absolute inset-x-3 bottom-3 flex justify-center">
      <figure className="max-w-2xl rounded-lg border bg-background/90 px-3 py-2 text-center shadow-sm sm:px-4 sm:py-2.5">
        {coach.status === "error" ? (
          <figcaption className="text-xs text-muted-foreground">Coach caption unavailable: {coach.message}</figcaption>
        ) : (
          <>
            <figcaption className="text-xs text-muted-foreground">
              Coach ·{" "}
              {coach.caption.fault ? (
                <>
                  top fault: <span style={{ color: YOU_COLOUR }}>{coach.caption.fault.label}</span>
                  <span className="hidden sm:inline"> · {coach.caption.fault.confidence} confidence</span>
                </>
              ) : (
                "no fault found"
              )}
            </figcaption>
            <blockquote className="mt-0.5 text-sm font-medium text-balance sm:text-base" style={{ color: GHOST_COLOUR }}>
              “{coach.caption.cue}”
            </blockquote>
          </>
        )}
      </figure>
    </div>
  );
}
