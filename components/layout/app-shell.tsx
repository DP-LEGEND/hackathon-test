import type { ReactNode } from "react";
import { AppHeader } from "./app-header";
import { MobileNav } from "./mobile-nav";
import { Sidebar, SidebarContent, type SidebarProps } from "./sidebar";

export function ContentContainer({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-5xl px-5 py-8 sm:px-8 sm:py-10 lg:px-10 lg:py-12">{children}</div>;
}

export function AppShell({ children, headerTitle, headerActions, ...sidebar }: SidebarProps & { children: ReactNode; headerTitle: ReactNode; headerActions?: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background">
      <a href="#main-content" className="sr-only fixed top-3 left-3 z-[100] rounded-lg bg-primary px-4 py-3 text-primary-foreground focus:not-sr-only">Skip to content</a>
      <Sidebar {...sidebar} />
      <div className="min-w-0 lg:pl-64">
        <AppHeader title={headerTitle} actions={headerActions} navigation={<MobileNav appName={sidebar.appName}><SidebarContent {...sidebar} /></MobileNav>} />
        <main id="main-content" tabIndex={-1} className="min-w-0 outline-none"><ContentContainer>{children}</ContentContainer></main>
      </div>
    </div>
  );
}
