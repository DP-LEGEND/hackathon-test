// Legend over the 3D view: orange = what you did, cyan = the ghost / the fix, and the
// PREDICTED ball paths when they're shown. When the fix doesn't change the ball, one shared
// path is drawn and the legend says so instead of showing two overlapping lines.

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import { OUTCOME_WORDS, type BallPath } from "./compare";
import { SAME_PATH_MESSAGE } from "./delta-panel";

export function SceneLegend({
  ghost,
  balls,
  monoDepth,
}: {
  /** What the ghost shows, e.g. "close stance 64.9°", and whether it's a real fix. Null = hidden. */
  ghost: { label: string; mock: boolean } | null;
  /**
   * `same`: both PREDICTED paths are identical. `noCorrection`: physics made no correction, so
   * they match because the ghost is your swing unchanged, not because a fix moved only the body.
   */
  balls: { you: BallPath; ghost: BallPath; same: boolean; noCorrection: boolean } | null;
  /** The swing's depth is estimated from one camera, not measured by stereo. */
  monoDepth: boolean;
}) {
  return (
    <div className="pointer-events-none absolute top-3 left-3 flex max-w-[calc(100%-1.5rem)] flex-col gap-1.5 rounded-xl border bg-background/92 px-3 py-2.5 text-sm shadow-lg sm:max-w-xs">
      <Key colour={YOU_COLOUR} name="You" detail={monoDepth ? "what you did · one-camera depth" : "what you did"} />
      {ghost && (
        <Key colour={GHOST_COLOUR} name="Ghost" detail={ghost.label}>
          {ghost.mock && (
            <Badge variant="outline" className="border-amber-400/50 text-amber-300">
              MOCK
            </Badge>
          )}
        </Key>
      )}
      {balls && (
        <div className="mt-1 flex flex-col gap-1 border-t pt-2">
          <p className="font-mono text-xs font-bold tracking-[0.14em]">PREDICTED BALL {balls.same ? "PATH" : "PATHS"}</p>
          <p className="text-xs text-muted-foreground">No real ball: from the ball model.</p>
          {balls.same ? (
            <>
              {balls.noCorrection ? (
                <p className="text-xs text-balance text-muted-foreground">No correction on this swing, so one path.</p>
              ) : (
                <p className="text-sm font-medium text-balance" style={{ color: GHOST_COLOUR }}>
                  {SAME_PATH_MESSAGE}.
                </p>
              )}
              <BallRow colour={YOU_COLOUR} who="You and ghost" ball={balls.you} />
            </>
          ) : (
            <>
              <BallRow colour={YOU_COLOUR} who="You" ball={balls.you} />
              <BallRow colour={GHOST_COLOUR} who="Ghost" ball={balls.ghost} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

function BallRow({ colour, who, ball }: { colour: string; who: string; ball: BallPath }) {
  return (
    <p className="flex items-center gap-2 text-xs tabular-nums">
      <span aria-hidden className="h-1 w-5 shrink-0 rounded-full" style={{ backgroundColor: colour }} />
      <span style={{ color: colour }}>{who}</span>
      <span className="text-muted-foreground">
        {OUTCOME_WORDS[ball.outcome]} · {ball.speedKmh} km/h
      </span>
    </p>
  );
}

function Key({
  colour,
  name,
  detail,
  children,
}: {
  colour: string;
  name: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      <span aria-hidden className="size-3 shrink-0 rounded-full" style={{ backgroundColor: colour }} />
      <span className="font-semibold" style={{ color: colour }}>
        {name}
      </span>
      <span className="text-muted-foreground">{detail}</span>
      {children}
    </p>
  );
}
