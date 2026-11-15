// A small badge on the court view when physics checked the PREDICTED ball against a real one
// (compare `validation`): the number predicted, the number seen, and how the real ball was found.
// Shown only when the file has a complete `validation`; the numbers are the file's, unchanged.

import { CircleCheck } from "lucide-react";
import type { BallValidation } from "./compare";
import { look } from "./look";

/** Decimal places a number has as written ("1.92" -> 2, "1.9" -> 1). */
function decimals(value: number): number {
  return String(value).split(".")[1]?.length ?? 0;
}

/**
 * Both numbers with the same decimal places, padding zeros only (1.92 and 1.9 -> "1.92", "1.90"),
 * so the pair reads evenly without rounding either one.
 */
function evenly(a: number, b: number): [string, string] {
  const places = Math.max(decimals(a), decimals(b));
  return [a.toFixed(places), b.toFixed(places)];
}

export function ValidationBadge({ validation }: { validation: BallValidation }) {
  const [predicted, tracked] = evenly(validation.predicted, validation.tracked);
  return (
    <div className="flex max-w-full flex-col gap-1 rounded-2xl border border-primary/40 bg-background/90 px-3.5 py-2.5 text-[13px] shadow-[0_8px_30px_rgb(0_0_0/0.35)]">
      <p className="flex items-start gap-2">
        <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
        <span>
          Checked against the real ball: <span className={look.value}>{predicted} m</span> predicted,{" "}
          <span className={look.value}>{tracked} m</span> tracked
        </span>
      </p>
      <p className="pl-6 text-[11px] text-muted-foreground">Method: {validation.method}</p>
    </div>
  );
}
