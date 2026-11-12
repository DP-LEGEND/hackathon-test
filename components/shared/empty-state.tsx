import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export function EmptyState({ title, description, icon, action }: { title: string; description?: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-5 py-16 text-center sm:py-20">
      <div aria-hidden="true" className="mb-5 flex size-12 items-center justify-center rounded-xl border bg-background text-muted-foreground shadow-xs [&_svg]:size-5">{icon ?? <Inbox />}</div>
      <h3 className="text-base font-medium tracking-tight">{title}</h3>
      {description && <p className="mt-2 max-w-sm text-sm leading-6 text-muted-foreground">{description}</p>}
      {action && <div className="mt-6 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
