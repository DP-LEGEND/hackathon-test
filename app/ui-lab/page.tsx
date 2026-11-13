import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Command } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { WorkflowLab } from "./workflow-lab";

export const metadata: Metadata = {
  title: "Workflow studio · UI Lab",
  description: "An isolated, mock-only AI workflow interface experiment.",
};

export default function UiLabPage() {
  return (
    <div className="min-h-dvh bg-muted/30 text-foreground [&_.text-muted-foreground]:text-foreground/75">
      <a href="#lab-main" className="sr-only rounded-lg bg-primary px-4 py-3 text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50">Skip to workspace</a>
      <header className="border-b bg-background">
        <div className="mx-auto flex min-h-16 max-w-7xl flex-wrap items-center justify-between gap-2 px-5 py-2 sm:px-8 lg:px-12">
          <div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Command aria-hidden="true" className="size-4" /></span><span className="font-semibold tracking-tight">Workflow studio</span><Badge variant="outline">UI lab</Badge></div>
          <Link href="/" aria-label="Back to starter" className="flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-md text-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"><ArrowLeft aria-hidden="true" className="size-4" /><span className="hidden sm:inline">Back to starter</span></Link>
        </div>
      </header>
      <main id="lab-main" tabIndex={-1} className="mx-auto max-w-7xl px-5 py-6 outline-none sm:px-8 sm:py-8 lg:px-12">
        <div className="mb-6 flex flex-col justify-between gap-3 lg:flex-row lg:items-end">
          <div><p className="mb-2 hidden font-mono text-sm tracking-widest text-muted-foreground uppercase sm:block">An experiment in focused work</p><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">From intent to a clear next step.</h1><p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">Give your agent a brief. Follow the work. Review an outcome you can act on.</p></div>
          <p className="max-w-sm border-l-2 pl-4 text-sm leading-5 text-muted-foreground">Interactive prototype. All progress and results are simulated locally. No AI provider is connected.</p>
        </div>
        <WorkflowLab />
        <footer className="mt-8 flex flex-wrap justify-between gap-3 border-t pt-5 text-sm text-muted-foreground"><span>Imperial AI Hackathon · Frontend experiment</span><span>No requests sent. Nothing stored.</span></footer>
      </main>
    </div>
  );
}
