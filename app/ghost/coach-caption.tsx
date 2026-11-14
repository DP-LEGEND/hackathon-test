// Coach caption laid over the 3D view, like a subtitle: the top fault, its cue and, when the
// ghost shows a different fix, the coach's ghost_note. Orange = what the player did (the
// fault), cyan = the fix (the cue).

import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import { groupNotJudged, listWords, type CoachCaption } from "./compare";

export type CaptionState =
  | { kind: "loading" }
  | { kind: "error"; message: string; onRetry: () => void }
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
          state.kind === "error" && "pointer-events-auto",
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
        {state.kind === "error" && (
          <div className="mt-1 flex flex-wrap items-center justify-center gap-x-3 gap-y-2">
            <p className="text-sm text-muted-foreground">The coach&apos;s call didn&apos;t load: {state.message}</p>
            <Button variant="outline" size="sm" onClick={state.onRetry}>
              <RotateCcw data-icon="inline-start" />
              Try again
            </Button>
          </div>
        )}
        {state.kind === "ready" && (
          <>
            <p
              className={cn("mt-1 font-medium text-balance", large ? "text-lg sm:text-2xl" : "text-sm sm:text-base")}
              style={{ color: YOU_COLOUR }}
            >
              {state.caption.fault
                ? tidyLabel(state.caption.fault.label)
                : state.caption.notJudged.length > 0
                  ? "No fault found in what the camera could see"
                  : "No fault found"}
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
            {state.caption.ghostNote && (
              <p className={cn("mt-1.5 text-balance text-muted-foreground", large ? "text-sm sm:text-base" : "text-xs sm:text-sm")}>
                {state.caption.ghostNote}
              </p>
            )}
            <NotJudgedNote caption={state.caption} large={large} />
          </>
        )}
      </figure>
    </div>
  );
}

/** One line saying some checks weren't judged, and which joints the camera couldn't see. */
function NotJudgedNote({ caption, large }: { caption: CoachCaption; large: boolean }) {
  const groups = groupNotJudged(caption.notJudged);
  if (groups.length === 0) return null;
  const checks = new Set(groups.flatMap((g) => g.checks)).size;
  const joints = [...new Set(groups.map((g) => g.joint).filter((j): j is string => j !== null))];
  return (
    <p className={cn("mt-1.5 text-balance text-muted-foreground", large ? "text-sm sm:text-base" : "text-xs sm:text-sm")}>
      Not judged: {checks} {checks === 1 ? "check" : "checks"}
      {joints.length > 0 && `, because the camera couldn't see the ${listWords(joints)}`}.
    </p>
  );
}
