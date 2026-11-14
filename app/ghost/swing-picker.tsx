// Step 1 of the demo: pick a swing. Saved samples always work; live swings appear when
// Dev's swing API (services/pipeline/server.py) is running on this computer.

import { ChevronRight, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "./colours";
import { GHOST_API_URL, type ApiState, type SwingEntry } from "./sources";

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
  return (
    <div className="flex flex-col gap-4">
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
                    <Badge variant={entry.origin === "api" ? "default" : "secondary"}>
                      {entry.origin === "api" ? "Live · swing API" : "Saved sample"}
                    </Badge>
                    <span className="text-base font-medium text-balance">{entry.label}</span>
                    <span className="text-sm text-muted-foreground">
                      {entry.coachFile ? "Coach's call ready · real ghosts" : "No coach call yet · ghosts at demo sizes"}
                    </span>
                    {entry.label !== entry.id && (
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
    <div className="flex flex-col gap-2 rounded-xl border border-dashed p-3 text-sm text-muted-foreground sm:p-4" role="status">
      {api.status === "checking" && <p>Looking for the swing API at {GHOST_API_URL}…</p>}
      {api.status === "local-only" && (
        <p>Showing saved samples. Live swings from the swing API load only when this page runs on your own computer.</p>
      )}
      {api.status === "offline" && (
        <>
          <p>
            The swing API isn&apos;t running at {GHOST_API_URL}, so these are the saved samples. To add live swings, run
            this from <code className="font-mono text-foreground">services/</code>:
          </p>
          <code className="w-fit rounded-md bg-muted px-2 py-1 font-mono text-xs break-all text-foreground">
            python -m uvicorn pipeline.server:app --port 8000
          </code>
          <div>{retry}</div>
        </>
      )}
      {api.status === "online" && (
        <>
          <p>
            {api.ids.length === 0
              ? "The swing API is running but has no processed swings. Point GHOST_SWINGS_DIR at a processed session (services/pipeline/README.md)."
              : `${api.ids.length} live ${api.ids.length === 1 ? "swing" : "swings"} from the swing API at ${GHOST_API_URL}.`}
          </p>
          <div>{retry}</div>
        </>
      )}
    </div>
  );
}
