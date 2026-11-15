// Ghost demo screen. Owner: Sammy.
// Pick a swing, see the coach's call, watch the ghost make the fix, then both PREDICTED ball
// paths on the court. Flow: ghost-demo.tsx. Data: app/ghost/README.md.

import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { Upload } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { GhostDemoFromUrl } from "./ghost-demo";

export const metadata: Metadata = {
  title: "Ghost · Swing coach",
  description: "See a squash swing you haven't played yet: the coach's one fix, your ghost making it, and both PREDICTED ball paths.",
};

export default function GhostPage() {
  return (
    <main className="dark flex flex-1 flex-col bg-background text-foreground">
      {/* Full width up to the site header's 1600 px, with its 64 px edges from lg up, so the 3D view grows with the window.
          No top padding: the site shell's --site-page-top sets the gap below the header on every page. */}
      <div className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col gap-6 px-4 pb-6 sm:px-6 lg:px-16 lg:pb-4">
        <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div className="flex flex-col gap-1">
            <p className="text-sm font-semibold tracking-[0.14em] text-muted-foreground uppercase">Ghost</p>
            <h1 className="text-base text-balance text-muted-foreground sm:text-lg">
              A squash swing you haven&apos;t played yet: the one fix that matters, shown by your ghost.
            </h1>
          </div>
          <Link href="/upload" className={buttonVariants({ variant: "outline" })}>
            <Upload data-icon="inline-start" aria-hidden />
            Try your own swing
          </Link>
        </header>
        {/* The demo reads ?swing= in the browser, so the prerendered page shows this until then. */}
        <Suspense
          fallback={
            <p role="status" className="rounded-xl border bg-card p-6 text-sm text-muted-foreground">
              Loading swings…
            </p>
          }
        >
          <GhostDemoFromUrl />
        </Suspense>
      </div>
    </main>
  );
}
