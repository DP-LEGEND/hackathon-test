// Ghost demo screen. Owner: Sammy.
// Pick a swing, see the coach's call, watch the ghost make the fix, then both PREDICTED ball
// paths on the court. Flow: ghost-demo.tsx. Data: app/ghost/README.md.

import type { Metadata } from "next";
import { GhostDemo } from "./ghost-demo";

export const metadata: Metadata = {
  title: "Ghost · Swing coach",
  description: "See a squash swing you haven't played yet: the coach's one fix, your ghost making it, and both PREDICTED ball paths.",
};

export default function GhostPage() {
  return (
    <main className="dark flex flex-1 flex-col bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6 lg:py-10">
        <header className="flex flex-col gap-1">
          <p className="text-sm font-semibold tracking-[0.14em] text-muted-foreground uppercase">Ghost</p>
          <h1 className="text-base text-balance text-muted-foreground sm:text-lg">
            A squash swing you haven&apos;t played yet: the one fix that matters, shown by your ghost.
          </h1>
        </header>
        <GhostDemo />
      </div>
    </main>
  );
}
