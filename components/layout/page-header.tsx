import type { ReactNode } from "react";

export type PageHeaderProps = { title: string; description?: string; eyebrow?: string; actions?: ReactNode };

export function PageHeader({ title, description, eyebrow, actions }: PageHeaderProps) {
  return (
    <div className="flex max-w-3xl flex-col items-start gap-5">
      <div className="min-w-0">
        {eyebrow && <p className="mb-3 text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">{eyebrow}</p>}
        <h1 className="break-words text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
        {description && <p className="mt-3 max-w-xl text-sm leading-6 text-muted-foreground sm:text-base">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
