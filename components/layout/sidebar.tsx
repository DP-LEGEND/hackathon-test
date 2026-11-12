import Link from "next/link";
import { Layers2 } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type NavigationItem = {
  label: string;
  href: string;
  icon?: ReactNode;
  active?: boolean;
};

export type SidebarProps = {
  appName: string;
  logo?: ReactNode;
  homeHref?: string;
  navigation: NavigationItem[];
  secondaryNavigation?: NavigationItem[];
  userArea?: ReactNode;
};

function Navigation({ items, label }: { items: NavigationItem[]; label: string }) {
  return (
    <nav aria-label={label} className="space-y-1">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          aria-current={item.active ? "page" : undefined}
          className={cn(
            "flex min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sidebar-ring [&_svg]:size-4 [&_svg]:shrink-0",
            item.active
              ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
              : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-foreground",
          )}
        >
          {item.icon}<span className="min-w-0 break-words">{item.label}</span>
          {item.active && <span aria-hidden="true" className="ml-auto size-1.5 shrink-0 rounded-full bg-current" />}
        </Link>
      ))}
    </nav>
  );
}

export function SidebarContent({ appName, logo, homeHref = "/", navigation, secondaryNavigation, userArea }: SidebarProps) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto bg-sidebar text-sidebar-foreground">
      <Link href={homeHref} className="mx-5 flex min-h-20 shrink-0 items-center gap-3 rounded-lg pr-8 font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-ring">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-sidebar-border bg-background shadow-xs">
          {logo ?? <Layers2 className="size-4" aria-hidden="true" />}
        </span>
        <span className="min-w-0 break-words">{appName}</span>
      </Link>
      <div className="flex-1 shrink-0 px-4 py-6">
        <p className="mb-3 px-3 text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">Workspace</p>
        <Navigation items={navigation} label="Primary navigation" />
      </div>
      <div className="shrink-0 space-y-4 p-4">
        {!!secondaryNavigation?.length && <Navigation items={secondaryNavigation} label="Secondary navigation" />}
        {userArea && <div className="border-t border-sidebar-border pt-4">{userArea}</div>}
      </div>
    </div>
  );
}

export function Sidebar(props: SidebarProps) {
  return <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-sidebar-border lg:block"><SidebarContent {...props} /></aside>;
}
