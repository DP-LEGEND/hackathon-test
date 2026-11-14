// Step 2 detail: every fault the coach found, with the number code measured and the
// threshold it crossed. The fault library decides; nothing here is computed.

import { YOU_COLOUR } from "./colours";
import { tidyLabel, type CaptionState } from "./coach-caption";
import { fixName, formatValue } from "./compare";

export function CoachDetails({ state }: { state: CaptionState }) {
  return (
    <section aria-labelledby="coach-details" className="flex flex-col gap-2 rounded-xl border bg-card p-3 sm:p-4">
      <h3 id="coach-details" className="text-sm font-medium">
        How the coach decided
      </h3>
      {state.kind === "loading" && <p className="text-sm text-muted-foreground">Loading…</p>}
      {state.kind === "error" && <p className="text-sm text-muted-foreground">{state.message}</p>}
      {state.kind === "none" && (
        <p className="text-sm text-muted-foreground">
          This swing came from the swing API, which has no coach endpoint yet. Next, you can pick any fix and see its
          ghost at a small fixed demo size.
        </p>
      )}
      {state.kind === "ready" && (
        <>
          <p className="text-xs text-muted-foreground">
            Code measured the {state.caption.stroke || "swing"}. The fault library ranks every number past its threshold,
            worst first, and the top one is the call.
          </p>
          {state.caption.faults.length === 0 ? (
            <p className="text-sm text-muted-foreground">Every measurement is inside its threshold.</p>
          ) : (
            <ol className="flex flex-col divide-y">
              {state.caption.faults.map((fault, i) => (
                <li key={fault.id} className="flex flex-col gap-0.5 py-2 first:pt-0 last:pb-0 sm:flex-row sm:items-baseline sm:gap-3">
                  <span className="w-6 shrink-0 font-mono text-xs text-muted-foreground">#{i + 1}</span>
                  <span className="font-medium sm:flex-1" style={{ color: YOU_COLOUR }}>
                    {tidyLabel(fault.label)}
                  </span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    measured {formatValue(fault.value, fault.unit)}
                    {fault.threshold !== null && <>, fault past {formatValue(fault.threshold, fault.unit)}</>}
                    {fault.severity !== null && <> · severity {fault.severity}</>} · {fault.confidence} confidence · fix:{" "}
                    {fixName(fault.fix).toLowerCase()}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
