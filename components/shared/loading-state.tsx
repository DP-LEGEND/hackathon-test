import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("rounded-md bg-muted motion-safe:animate-pulse", className)} />;
}

export function LoadingState({ label = "Loading content…" }: { label?: string }) {
  return (
    <div role="status" className="mx-auto w-full max-w-lg space-y-6 px-6 py-16 sm:py-20">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="space-y-3"><Skeleton className="h-5 w-2/5" /><Skeleton className="h-3 w-4/5" /></div>
      <div aria-hidden="true" className="space-y-3">{["w-full", "w-5/6", "w-2/3"].map(width => <Skeleton key={width} className={cn("h-11", width)} />)}</div>
      <p aria-hidden="true" className="text-center text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
