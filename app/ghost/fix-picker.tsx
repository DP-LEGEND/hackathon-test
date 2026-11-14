// Fix picker: which coaching fix the ghost shows. One button per fix physics can make.
// "Coach's pick" = the fix the coach starts the ghost on; "Coach flagged" = another fault the
// coach found. The rest are real ghost edits at a fixed demo size. A fix physics can't apply
// to this swing stays visible (and focusable) with its reason.

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "./colours";
import { fixName, formatValue, type CoachFault } from "./compare";
import type { FixOption } from "./sources";

/** "Not available: the wrist already…" -> "the wrist already…" (the list says it's unavailable). */
function reasonText(reason: string): string {
  const text = reason.replace(/^not available:\s*/i, "");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function FixPicker({
  fixes,
  selected,
  loading,
  faults,
  coachPick,
  coached,
  onSelect,
}: {
  fixes: FixOption[];
  selected: string | null;
  /** The selected fix's ghost is still being fetched or computed. */
  loading: boolean;
  /** Faults the coach found, worst first. */
  faults: CoachFault[];
  /** The fix the coach starts the ghost on. */
  coachPick: string | null;
  /** False when the coach's call couldn't be loaded. */
  coached: boolean;
  onSelect: (fixId: string) => void;
}) {
  const unavailable = fixes.filter((f) => f.unavailable !== null);
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-labelledby="fix-picker-label" className="flex flex-wrap items-center gap-2">
        <p id="fix-picker-label" className="mr-1 text-sm text-muted-foreground">
          Ghost shows the fix
        </p>
        {fixes.map((fix) => {
          const on = fix.id === selected;
          const off = fix.unavailable !== null;
          const flagged = fix.id !== coachPick && faults.some((f) => f.fix === fix.id);
          return (
            <Button
              key={fix.id}
              variant="outline"
              aria-pressed={on}
              aria-busy={on && loading}
              aria-describedby={off ? `fix-why-${fix.id}` : undefined}
              disabled={off}
              focusableWhenDisabled
              onClick={() => onSelect(fix.id)}
              className={cn(on && "bg-muted dark:bg-muted", off && "line-through decoration-muted-foreground/60")}
              style={on ? { borderColor: GHOST_COLOUR } : undefined}
            >
              <span
                aria-hidden
                className={cn("size-2 rounded-full", on && loading && "motion-safe:animate-pulse")}
                style={{ backgroundColor: on ? GHOST_COLOUR : "transparent", boxShadow: `inset 0 0 0 1.5px ${GHOST_COLOUR}` }}
              />
              {fixName(fix.id)}
              {!off && <span className="font-normal text-muted-foreground tabular-nums">{formatValue(fix.amount, fix.unit)}</span>}
              {fix.id === coachPick && <Badge variant="secondary">Coach&apos;s pick</Badge>}
              {flagged && <Badge variant="secondary">Coach flagged</Badge>}
              {off && <Badge variant="outline">Unavailable</Badge>}
            </Button>
          );
        })}
      </div>
      {unavailable.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-sm">
          {unavailable.map((f) => (
            <li key={f.id} id={`fix-why-${f.id}`} className="text-muted-foreground">
              <span className="font-medium text-foreground">{fixName(f.id)} isn&apos;t available here.</span>{" "}
              {reasonText(f.unavailable ?? "")}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        {coached
          ? "Fixes the coach didn't flag are real ghost edits at a small demo size, for comparison."
          : "Without the coach's call, every fix uses a small fixed demo size."}
      </p>
    </div>
  );
}
