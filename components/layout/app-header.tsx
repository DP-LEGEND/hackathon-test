import type { ReactNode } from "react";

export function AppHeader({ navigation, title, actions }: { navigation?: ReactNode; title: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex min-h-20 min-w-0 items-center justify-between gap-4 border-b bg-background px-4 sm:px-8 lg:px-10">
      <div className="flex min-w-0 items-center gap-3">{navigation}<div className="min-w-0 break-words text-sm font-medium">{title}</div></div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
