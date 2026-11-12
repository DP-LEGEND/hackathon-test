import type { ReactNode } from "react";

export function SectionHeader({ title, description, actions, id }: { title: string; description?: string; actions?: ReactNode; id?: string }) {
  return (
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
      <div className="min-w-0"><h2 id={id} className="break-words text-base font-semibold tracking-tight">{title}</h2>{description && <p className="mt-1.5 text-sm leading-6 text-muted-foreground">{description}</p>}</div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
