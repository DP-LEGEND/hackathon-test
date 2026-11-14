// Step 1 of the demo: pick a swing. The demo swing comes first with a big Start button.
// Saved samples always work; live swings appear when Dev's Python service is running
// (reached through the same-origin /api proxy).

import { ChevronRight, Play, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "./colours";
import type { ApiState, SwingEntry } from "./sources";

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
    <div className="flex flex-col gap-4">
      {demo && (
        <div>
          <Button size="lg" className="h-11 px-4 text-base" onClick={() => onPick(demo.key)}>
            <Play data-icon="inline-start" />
            Start with the demo swing
          </Button>
        </div>
      )}
      {catalogue.status === "loading" && (
        <p role="status" className="rounded-xl border bg-card p-6 text-sm text-muted-foreground">
          Loading swings…
        </p>
      )}
      {catalogue.status === "error" && (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border bg-card p-6">
          <p className="text-sm">The saved swings couldn&apos;t load: {catalogue.message}</p>
          <Button variant="outline" onClick={catalogue.onRetry}>
            <RotateCcw data-icon="inline-start" />
            Try again
          </Button>
        </div>
      )}
      {catalogue.status === "ready" && entries.length === 0 && (
        <p className="rounded-xl border bg-card p-6 text-sm text-muted-foreground">No swings yet.</p>
      )}
      {entries.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {entries.map((entry) => {
            const picked = entry.key === selectedKey;
            return (
              <li key={entry.key}>
                <button
                  type="button"
                  onClick={() => onPick(entry.key)}
                  aria-current={picked ? "true" : undefined}
                  className={cn(
                    "group flex h-full w-full items-start gap-3 rounded-xl border bg-card p-4 text-left transition-colors outline-none",
                    "hover:bg-muted focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
                  )}
                  style={picked ? { borderColor: GHOST_COLOUR } : undefined}
                >
                  <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <span className="flex flex-wrap gap-1.5">
                      <Badge variant={entry.origin === "api" ? "default" : "secondary"}>
                        {entry.origin === "api" ? "Live" : "Saved sample"}
                      </Badge>
                      {entry.isDefault && <Badge variant="outline">Demo swing</Badge>}
                    </span>
                    <span className="text-base font-medium text-balance">{entry.label}</span>
                    <span className="text-sm text-muted-foreground">
                      {entry.origin === "api"
                        ? "The coach measures it live; ghosts are computed on request"
                        : "Coach's call and ghosts saved from the Python service"}
                    </span>
                    {entry.origin === "sample" && (
                      <span className="font-mono text-xs break-all text-muted-foreground">{entry.id}</span>
                    )}
                  </span>
                  <ChevronRight
                    aria-hidden
                    className="mt-1 size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                  />
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
    <Button variant="outline" size="sm" onClick={onRetry} disabled={api.status === "checking"}>
      <RotateCcw data-icon="inline-start" />
      Check again
    </Button>
  );
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-dashed p-3 text-sm text-muted-foreground sm:p-4">
      {api.status === "checking" && <p role="status">Looking for live swings…</p>}
      {api.status === "offline" && (
        <>
          <p role="status">
            The live Python service isn&apos;t running, so these are the saved samples. To add live swings, run this
            from the repo folder:
          </p>
          <code className="w-fit rounded-md bg-muted px-2 py-1 font-mono text-xs break-all text-foreground">
            python -m uvicorn pipeline.server:app --app-dir services --port 8000
          </code>
          <div>{retry}</div>
        </>
      )}
      {api.status === "online" && (
        <>
          <p role="status">
            {api.swings.length === 0
              ? "The live service is running but has no processed swings. Point GHOST_SWINGS_DIR at a processed session (services/pipeline/README.md)."
              : `${api.swings.length} live ${api.swings.length === 1 ? "swing" : "swings"} from the Python service.`}
          </p>
          <div>{retry}</div>
        </>
      )}
    </div>
  );
}
