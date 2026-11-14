// Fix picker: which coaching fix the ghost shows. One button per compare file.
// A fix is "flagged" when the coach found the fault it fixes on this swing.

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "./colours";
import { fixName, formatValue, type CoachFault, type CompareResult } from "./compare";

export function FixPicker({
  compares,
  selected,
  faults,
  onSelect,
}: {
  compares: CompareResult[];
  selected: string | null;
  /** Faults the coach found, worst first. Empty if the coach file didn't load. */
  faults: CoachFault[];
  onSelect: (fixId: string) => void;
}) {
  const top = faults[0];
  const topHasGhost = !top || compares.some((c) => c.fix.id === top.fix);
  const nextWithGhost = faults.find((f) => compares.some((c) => c.fix.id === f.fix));
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-labelledby="fix-picker-label" className="flex flex-wrap items-center gap-2">
        <p id="fix-picker-label" className="mr-1 text-sm text-muted-foreground">
          Ghost shows the fix
        </p>
        {compares.map(({ fix }) => {
          const on = fix.id === selected;
          const rank = faults.findIndex((f) => f.fix === fix.id);
          return (
            <Button
              key={fix.id}
              variant="outline"
              aria-pressed={on}
              onClick={() => onSelect(fix.id)}
              className={cn(on && "bg-muted dark:bg-muted")}
              style={on ? { borderColor: GHOST_COLOUR } : undefined}
            >
              <span
                aria-hidden
                className="size-2 rounded-full"
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
        {!topHasGhost && top && (
          <>
            The coach&apos;s top fix, {fixName(top.fix).toLowerCase()}, has no ghost yet
            {nextWithGhost ? `, so the ghost starts on its next one, ${fixName(nextWithGhost.fix).toLowerCase()}. ` : ". "}
          </>
        )}
        Fixes the coach didn&apos;t flag are real ghost edits at a small demo size, for comparison.
      </p>
    </div>
  );
}
