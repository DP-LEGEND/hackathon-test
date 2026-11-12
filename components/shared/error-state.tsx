import type { ReactNode } from "react";
import { CircleAlert } from "lucide-react";

export function ErrorState({ title = "Something went wrong", description = "We couldn’t load this content. Please try again.", action }: { title?: string; description?: string; action?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-col items-center px-5 py-16 text-center sm:py-20">
      <span className="mb-5 flex size-12 items-center justify-center rounded-xl border border-destructive/20 bg-destructive/5 text-destructive"><CircleAlert aria-hidden="true" className="size-5" /></span>
      <h3 className="text-base font-medium tracking-tight">{title}</h3>
      <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
