"use client";

import { useState } from "react";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "./empty-state";
import { LoadingState } from "./loading-state";
import { ErrorState } from "./error-state";

const states = ["Empty", "Loading", "Error"] as const;
type PreviewState = typeof states[number];

export function StatePreview() {
  const [state, setState] = useState<PreviewState>("Empty");
  return (
    <div className="overflow-hidden rounded-xl border bg-card text-card-foreground">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4 sm:px-6">
        <p className="text-xs font-medium text-muted-foreground">Component preview</p>
        <div role="group" aria-label="Preview a content state" className="flex gap-1 rounded-lg bg-muted p-1">
          {states.map(item => <Button key={item} variant={state === item ? "outline" : "ghost"} size="sm" aria-pressed={state === item} onClick={() => setState(item)} className="h-9 px-3">{item}</Button>)}
        </div>
      </div>
      <div className="flex min-h-96 items-center justify-center">
        {state === "Empty" && <EmptyState title="A space for what’s next" description="Your content will live here. Start with the task that matters, and make this space your own." action={<Button nativeButton={false} variant="outline" className="h-10" render={<a href="#shell-details" />}>Explore the starter <ArrowRight aria-hidden="true" /></Button>} />}
        {state === "Loading" && <LoadingState label="Preparing your content…" />}
        {state === "Error" && <ErrorState description="This is an example error state. Give people a clear explanation and a way to recover." action={<Button variant="outline" className="h-10" onClick={() => setState("Empty")}><RotateCcw aria-hidden="true" />Reset preview</Button>} />}
      </div>
    </div>
  );
}
