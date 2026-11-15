// Step 1 of the demo: pick a swing. The demo swing comes first with a big Start button.
// Saved samples always work; live swings appear when Dev's Python service is running
// (reached through the same-origin /api proxy).

import { ArrowUpRight, Play, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { look } from "./look";
import type { ApiState, SwingEntry } from "./sources";
import { StateCard } from "./state-card";

export type CatalogueState =
  | { status: "loading" }
  | { status: "error"; message: string; onRetry: () => void }
  | { status: "ready" };

export function SwingPicker({
  catalogue,
  entries,
  api,
  selectedKey,
  onPick,
  onRetryApi,
}: {
  catalogue: CatalogueState;
  entries: SwingEntry[];
  api: ApiState;
  selectedKey: string | null;
  onPick: (key: string) => void;
  onRetryApi: () => void;
}) {
  const demo = entries.find((e) => e.isDefault);
  return (
    <div className="flex flex-col gap-5">
      {demo && (
        <div>
          <Button
            size="lg"
            className="h-12 rounded-full px-6 text-base sm:h-14 sm:px-8 sm:text-[17px]"
            onClick={() => onPick(demo.key)}
          >
            <Play data-icon="inline-start" />
            Start with the demo swing
          </Button>
        </div>
      )}
      {catalogue.status === "loading" && (
        <StateCard tone="loading" role="status">
          Loading swings…
        </StateCard>
      )}
      {catalogue.status === "error" && (
        <StateCard
          tone="error"
          role="alert"
          actions={
            <Button variant="outline" className={look.pill} onClick={catalogue.onRetry}>
              <RotateCcw data-icon="inline-start" />
              Try again
            </Button>
          }
        >
          <p>The saved swings couldn&apos;t load: {catalogue.message}</p>
        </StateCard>
      )}
      {catalogue.status === "ready" && entries.length === 0 && <StateCard tone="empty">No swings yet.</StateCard>}
      {entries.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3">
          {entries.map((entry) => {
            const picked = entry.key === selectedKey;
            return (
              <li key={entry.key}>
                <button
                  type="button"
                  onClick={() => onPick(entry.key)}
                  aria-current={picked ? "true" : undefined}
                  className={cn(
                    look.card,
                    "group flex h-full w-full items-start gap-3 p-5 text-left transition-colors hover:border-primary/50",
                    picked && "border-primary bg-accent",
                  )}
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-2">
                    <span className="flex flex-wrap gap-1.5">
                      <Badge variant={entry.origin === "api" ? "default" : "secondary"} className={cn(look.chip, "uppercase")}>
                        {entry.origin === "api" ? "Live" : "Saved sample"}
                      </Badge>
                      {entry.isDefault && (
                        <Badge variant="outline" className={cn(look.chip, "uppercase")}>
                          Demo swing
                        </Badge>
                      )}
                    </span>
                    <span className={cn(look.title, "text-balance")}>{entry.label}</span>
                    <span className="text-sm leading-relaxed text-muted-foreground">
                      {entry.origin === "api"
                        ? "The coach measures it live; ghosts are computed on request"
                        : "Coach's call and ghosts saved from the Python service"}
                    </span>
                    <span className="font-mono text-xs break-all text-muted-foreground">{entry.id}</span>
                  </span>
                  <span
                    aria-hidden
                    className="grid size-9 shrink-0 place-items-center rounded-full border text-muted-foreground transition-colors group-hover:border-primary group-hover:text-primary"
                  >
                    <ArrowUpRight className="size-4" />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <ApiStatus api={api} onRetry={onRetryApi} />
    </div>
  );
}

function ApiStatus({ api, onRetry }: { api: ApiState; onRetry: () => void }) {
  const retry = (
    <Button variant="outline" size="sm" className={look.pill} onClick={onRetry} disabled={api.status === "checking"}>
      <RotateCcw data-icon="inline-start" />
      Check again
    </Button>
  );
  const dot = (
    <span
      aria-hidden
      className={cn(
        "mt-1.5 size-2 shrink-0 rounded-full",
        api.status === "online" ? "bg-primary" : "bg-muted-foreground",
        api.status === "checking" && "motion-safe:animate-pulse",
      )}
    />
  );
  return (
    <div className="flex flex-col gap-3 rounded-[20px] border border-dashed p-4 text-sm leading-relaxed text-muted-foreground sm:p-5">
      {api.status === "checking" && (
        <p role="status" className="flex gap-2.5">
          {dot}
          <span>Looking for live swings…</span>
        </p>
      )}
      {api.status === "offline" && (
        <>
          <p role="status" className="flex gap-2.5">
            {dot}
            <span>The live Python service isn&apos;t running, so these are the saved samples.</span>
          </p>
          {/* The shell command is for the team, not judges: folded away, word for word. */}
          <details className="pl-[18px]">
            <summary className="w-fit cursor-pointer rounded-sm text-foreground underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              For developers
            </summary>
            <div className="mt-2 flex flex-col gap-2">
              <p>To add live swings, run this from the repo folder:</p>
              <code className="w-fit max-w-full rounded-xl border bg-(--media) px-3 py-2 font-mono text-xs break-all text-foreground">
                python -m uvicorn pipeline.server:app --app-dir services --port 8000
              </code>
            </div>
          </details>
          <div>{retry}</div>
        </>
      )}
      {api.status === "online" && (
        <>
          <p role="status" className="flex gap-2.5">
            {dot}
            <span>
              {api.swings.length === 0
                ? "The live service is running but has no processed swings. Point GHOST_SWINGS_DIR at a processed session (services/pipeline/README.md)."
                : `${api.swings.length} live ${api.swings.length === 1 ? "swing" : "swings"} from the Python service.`}
            </span>
          </p>
          <div>{retry}</div>
        </>
      )}
    </div>
  );
}
