// Coach caption laid over the 3D view, like a subtitle: the top fault and its cue.
// Orange = what the player did (the fault), cyan = the fix (the cue).

import { cn } from "@/lib/utils";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import type { CoachCaption } from "./compare";

export type CaptionState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  /** Nobody has coached this swing (live swings: the swing API has no coach endpoint yet). */
  | { kind: "none" }
  | { kind: "ready"; caption: CoachCaption };

/** "Stance 80 deg open" -> "Stance 80° open". Wording only; the number is the file's. */
export function tidyLabel(label: string): string {
  return label.replace(/(\d) deg\b/g, "$1°");
}

export function CoachCaptionBar({ state, size }: { state: CaptionState; size: "large" | "compact" }) {
  const large = size === "large";
  return (
    <div className="pointer-events-none absolute inset-x-3 bottom-3 flex justify-center">
      <figure
        className={cn(
          "w-full max-w-3xl rounded-xl border bg-background/92 text-center shadow-lg",
          large ? "px-4 py-3 sm:px-6 sm:py-4" : "px-3 py-2 sm:px-5 sm:py-2.5",
        )}
        aria-live="polite"
      >
        <figcaption className="text-[0.7rem] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
          Coach&apos;s call
          {state.kind === "ready" && state.caption.fault && (
            <span className="font-normal tracking-normal normal-case"> · {state.caption.fault.confidence} confidence</span>
          )}
        </figcaption>
        {state.kind === "loading" && <p className="mt-1 text-sm text-muted-foreground">Reading the coach&apos;s call…</p>}
        {state.kind === "error" && <p className="mt-1 text-sm text-muted-foreground">Coach caption unavailable: {state.message}</p>}
        {state.kind === "none" && (
          <p className={cn("mt-1 text-muted-foreground", large ? "text-base sm:text-lg" : "text-sm")}>
            No coach call for this swing yet. Pick a fix to see its ghost.
          </p>
        )}
        {state.kind === "ready" && (
          <>
            <p
              className={cn("mt-1 font-medium text-balance", large ? "text-lg sm:text-2xl" : "text-sm sm:text-base")}
              style={{ color: YOU_COLOUR }}
            >
              {state.caption.fault ? tidyLabel(state.caption.fault.label) : "No fault found"}
            </p>
            <blockquote
              className={cn(
                "mt-1 leading-tight font-semibold text-balance",
                large ? "text-2xl sm:text-4xl" : "text-lg sm:text-2xl",
              )}
              style={{ color: GHOST_COLOUR }}
            >
              “{state.caption.cue}”
            </blockquote>
          </>
        )}
      </figure>
    </div>
  );
}
