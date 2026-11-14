// While the clip is sent and processed. The upload progress is real. The service answers only
// once, when pose, coach and ghost are all saved, so after the upload the steps move on a timer
// and the panel says they're a guide. Cyan = the ghost being built.

import { useEffect, useState, type Ref } from "react";
import { Check, Circle, LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "../ghost/colours";

const STEPS = ["Uploading your clip", "Finding your swing…", "Measuring…", "Building your ghost…"];
/** When steps 1–3 start, in ms after the upload finished. A guide, not a measurement. */
const STEP_STARTS_MS = [0, 12_000, 24_000];

export function ProgressPanel({
  startedAt,
  uploadedAt,
  progress,
  onCancel,
  headingRef,
}: {
  /** Date.now() when Build was pressed. */
  startedAt: number;
  /** Date.now() when the upload finished, or null while it's still uploading. */
  uploadedAt: number | null;
  /** Upload fraction 0–1, or null when the browser can't tell. */
  progress: number | null;
  onCancel: () => void;
  headingRef: Ref<HTMLHeadingElement>;
}) {
  const [now, setNow] = useState(startedAt);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, []);

  const step = uploadedAt === null ? 0 : STEP_STARTS_MS.filter((ms) => Math.max(0, now - uploadedAt) >= ms).length;
  const percent = progress === null ? null : Math.round(progress * 100);

  return (
    <section aria-labelledby="progress-heading" className="flex flex-col gap-4 rounded-2xl border bg-card p-4 sm:p-5">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="progress-heading" ref={headingRef} tabIndex={-1} className="text-base font-medium outline-none">
          Working on your swing
        </h2>
        <p className="font-mono text-sm text-muted-foreground tabular-nums">
          <span className="sr-only">Time so far: </span>
          {formatElapsed(now - startedAt)}
        </p>
      </div>

      <ol className="flex flex-col gap-3">
        {STEPS.map((label, index) => {
          const done = index < step;
          const active = index === step;
          return (
            <li
              key={label}
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex items-center gap-3 text-sm",
                active ? "font-medium text-foreground" : done ? "text-muted-foreground" : "text-muted-foreground/60",
              )}
            >
              <span
                aria-hidden
                className="flex size-5 shrink-0 items-center justify-center"
                style={active || done ? { color: GHOST_COLOUR } : undefined}
              >
                {done ? (
                  <Check className="size-4" />
                ) : active ? (
                  <LoaderCircle className="size-4 motion-safe:animate-spin" />
                ) : (
                  <Circle className="size-2" />
                )}
              </span>
              <span>
                {label}
                {index === 0 && active && percent !== null && <span className="tabular-nums"> · {percent}%</span>}
                <span className="sr-only">{done ? ", done" : active ? ", in progress" : ""}</span>
              </span>
            </li>
          );
        })}
      </ol>

      {step === 0 && (
        <div
          role="progressbar"
          aria-label="Upload"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent ?? undefined}
          className="h-1.5 overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full rounded-full transition-[width] duration-300"
            style={{ width: `${percent ?? 0}%`, backgroundColor: GHOST_COLOUR }}
          />
        </div>
      )}

      {/* Step changes only, so a screen reader isn't read every percent. */}
      <p role="status" aria-live="polite" className="sr-only">
        {STEPS[step]}
      </p>

      <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-pretty text-muted-foreground">
          {step === 0
            ? "Keep this page open while the clip uploads."
            : "The service reports back once, when your ghost is ready, so these steps are a rough guide. It can take a minute or two."}
        </p>
        <Button type="button" variant="outline" className="w-fit shrink-0" onClick={onCancel}>
          <X data-icon="inline-start" />
          {step === 0 ? "Cancel upload" : "Stop waiting"}
        </Button>
      </div>
    </section>
  );
}

function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
