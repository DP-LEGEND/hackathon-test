// Step 2 detail: every fault the coach found, with the number code measured and the
// threshold it crossed, then what it didn't judge and why. The fault library decides;
// nothing here is computed.

import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { YOU_COLOUR } from "./colours";
import { checkedEverything, tidyLabel, type CaptionState } from "./coach-caption";
import { fixName, formatValue, listWords, notCheckedFaults, type CoachCaption } from "./compare";
import { look } from "./look";
import { ReasonList } from "./reason-list";

export function CoachDetails({ state }: { state: CaptionState }) {
  return (
    <section aria-labelledby="coach-details" className={cn(look.card, look.pad, "flex flex-col gap-3")}>
      <h3 id="coach-details" className={look.title}>
        How the coach decided
      </h3>
      {state.kind === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
      {state.kind === "error" && (
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-muted-foreground">The coach&apos;s call didn&apos;t load: {state.message}</p>
          <Button variant="outline" size="sm" className={look.pill} onClick={state.onRetry}>
            <RotateCcw data-icon="inline-start" />
            Try again
          </Button>
        </div>
      )}
      {state.kind === "ready" && (
        <>
          <p className="text-[13px] leading-relaxed text-muted-foreground">
            Code measured the {state.caption.stroke || "swing"}
            {`. ${rankingSentence(state.caption)}`}
          </p>
          {state.caption.faults.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {checkedEverything(state.caption)
                ? "Every measurement is inside its threshold."
                : "No fault found in what was checked: every measurement the coach could make is inside its threshold. What it couldn't check is below."}
            </p>
          ) : (
            <ol className="flex flex-col divide-y rounded-2xl border bg-(--media) px-4">
              {state.caption.faults.map((fault, i) => (
                <li key={fault.id} className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-4">
                  <span className="w-6 shrink-0 font-mono text-xs text-muted-foreground">#{i + 1}</span>
                  <span className="font-medium sm:flex-1" style={{ color: YOU_COLOUR }}>
                    {tidyLabel(fault.label)}
                  </span>
                  <span className="text-xs leading-relaxed text-muted-foreground tabular-nums sm:text-right">
                    measured <span className={look.value}>{formatValue(fault.value, fault.unit)}</span>
                    {fault.threshold !== null && (
                      <>
                        , fault past <span className={look.value}>{formatValue(fault.threshold, fault.unit)}</span>
                      </>
                    )}
                    {fault.severity !== null && <> · severity {fault.severity}</>} · {fault.confidence} confidence · fix:{" "}
                    {fixName(fault.fix).toLowerCase()}
                    {fault.fix === state.caption.ghostFix && " · the ghost shows this"}
                  </span>
                </li>
              ))}
            </ol>
          )}
          {state.caption.ghostNote && <p className="text-xs text-muted-foreground">{state.caption.ghostNote}</p>}
          <NotJudgedList caption={state.caption} />
        </>
      )}
    </section>
  );
}

/**
 * How the list is ordered. The fault library ranks by severity (coaching priority breaks ties),
 * so the wrist-sensor wording shows only when rolled_wrist is the coach's top fault.
 */
function rankingSentence(caption: CoachCaption): string {
  return caption.fault?.id === "rolled_wrist"
    ? "A wrist-sensor fault leads; the rest are ranked worst first."
    : "The fault library ranks every number past its threshold, worst first, and the top one is the call.";
}

/**
 * Checks the coach skipped instead of judging them from a guessed joint, then every fault it
 * couldn't check (e.g. rolled_wrist without a wrist sensor), both as the coach listed them.
 * Shown, never hidden.
 */
function NotJudgedList({ caption }: { caption: CoachCaption }) {
  if (checkedEverything(caption)) return null;
  return (
    <div className="flex flex-col gap-1.5 border-t pt-3">
      <ReasonList label="Not judged" items={caption.notJudged} />
      {caption.notMeasured.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Not checked on this swing (a measurement it needs is missing): {listWords(notCheckedFaults(caption))}.
        </p>
      )}
    </div>
  );
}
