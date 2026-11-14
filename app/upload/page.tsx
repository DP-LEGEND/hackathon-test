// "Try your own swing": send one clip to the pipeline, then open the new swing in /ghost.
// Owner: Sammy. Flow: upload-form.tsx. Request, answers and limits: README.md.

import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { UploadForm } from "./upload-form";

export const metadata: Metadata = {
  title: "Try your own swing · Ghost",
  description: "Upload one squash swing: the coach names the one fix that matters, and your ghost makes it.",
};

export default function UploadPage() {
  return (
    <main className="dark flex flex-1 flex-col bg-background text-foreground">
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-6 sm:px-6 lg:py-10">
        <header className="flex flex-col gap-3">
          <Link
            href="/ghost"
            className="inline-flex w-fit items-center gap-1.5 rounded-sm text-sm font-semibold tracking-[0.14em] text-muted-foreground uppercase transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <ArrowLeft aria-hidden className="size-3.5" />
            Ghost
          </Link>
          <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">Try your own swing</h1>
          <p className="max-w-prose text-base text-pretty text-muted-foreground sm:text-lg">
            Film one swing on your phone and drop the video here. Code measures it, the coach names the one fix that
            matters, and your ghost makes it.
          </p>
        </header>
        <UploadForm />
      </div>
    </main>
  );
}
