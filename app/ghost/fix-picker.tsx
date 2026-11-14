// Fix picker: which coaching fix the ghost shows. One button per fix physics can make.
// "Coach's pick" / "Coach flagged" = the coach found that fault on this swing; the rest
// are real ghost edits at a fixed demo size.

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "./colours";
import { fixName, formatValue, type CoachFault } from "./compare";
import type { FixOption } from "./sources";

export function FixPicker({
  fixes,
  selected,
  loading,
  faults,
  coached,
  onSelect,
}: {
  fixes: FixOption[];
  selected: string | null;
  /** The selected fix's ghost is still being fetched or computed. */
  loading: boolean;
  /** Faults the coach found, worst first. */
  faults: CoachFault[];
  /** False when no coach has looked at this swing. */
  coached: boolean;
  onSelect: (fixId: string) => void;
}) {
  const unavailable = fixes.filter((f) => f.unavailable);
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-labelledby="fix-picker-label" className="flex flex-wrap items-center gap-2">
        <p id="fix-picker-label" className="mr-1 text-sm text-muted-foreground">
          Ghost shows the fix
        </p>
        {fixes.map((fix) => {
          const on = fix.id === selected;
          const rank = faults.findIndex((f) => f.fix === fix.id);
          return (
            <Button
              key={fix.id}
              variant="outline"
              aria-pressed={on}
              aria-busy={on && loading}
              disabled={fix.unavailable !== null}
              onClick={() => onSelect(fix.id)}
              className={cn(on && "bg-muted dark:bg-muted")}
              style={on ? { borderColor: GHOST_COLOUR } : undefined}
            >
              <span
                aria-hidden
                className={cn("size-2 rounded-full", on && loading && "motion-safe:animate-pulse")}
                style={{ backgroundColor: on ? GHOST_COLOUR : "transparent", boxShadow: `inset 0 0 0 1.5px ${GHOST_COLOUR}` }}
              />
              {fixName(fix.id)}
              <span className="font-normal text-muted-foreground tabular-nums">{formatValue(fix.amount, fix.unit)}</span>
              {rank === 0 && <Badge variant="secondary">Coach&apos;s pick</Badge>}
              {rank > 0 && <Badge variant="secondary">Coach flagged</Badge>}
            </Button>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">
        {coached
          ? "Fixes the coach didn't flag are real ghost edits at a small demo size, for comparison."
          : "No coach has looked at this swing, so every fix uses a small fixed demo size."}
        {unavailable.map((f) => ` ${fixName(f.id)} can't be applied: ${f.unavailable}`).join("")}
      </p>
    </div>
  );
}
