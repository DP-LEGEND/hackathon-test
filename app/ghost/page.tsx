// Ghost demo screen. Owner: Sammy.
// 3D replay of your swing (orange) with the ghost (cyan) aligned at contact, both PREDICTED
// ball paths on the court, the coach's caption and a fix picker. Data: app/ghost/README.md.

import type { Metadata } from "next";
import { GhostReplay } from "./ghost-replay";

export const metadata: Metadata = {
  title: "Ghost · Swing replay",
  description: "Your squash swing and its ghost in 3D, with the coach's fix and both PREDICTED ball paths.",
};

export default function GhostPage() {
  return (
    <main className="dark flex flex-1 flex-col bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-5 px-4 py-6 sm:px-6 lg:py-10">
        <header className="flex flex-col gap-1">
          <p className="text-sm text-muted-foreground">Ghost · swing replay</p>
          <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
            Your swing and its ghost, aligned at contact
          </h1>
        </header>
        <GhostReplay />
      </div>
    </main>
  );
}
