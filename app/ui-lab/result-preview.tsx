import { ArrowUpRight, Check, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

const priorities = [
  { number: "01", title: "Make one promise", detail: "Choose a single user and an outcome that can be demonstrated in under two minutes." },
  { number: "02", title: "Build the complete loop", detail: "Connect input, agent execution, and a useful result before expanding the feature set." },
  { number: "03", title: "Design for the unexpected", detail: "Make progress visible, preserve the brief on failure, and provide an obvious retry." },
];

export function ResultPreview({ brief, onReset }: { brief: string; onReset: () => void }) {
  return (
    <article className="flex flex-1 flex-col">
      <div className="grid gap-6 p-5 sm:p-7 lg:grid-cols-2">
        <div><p className="mb-3 flex items-center gap-2 font-mono text-sm text-foreground"><Check aria-hidden="true" className="size-3.5" />SIMULATION COMPLETE</p><h3 className="text-2xl font-semibold tracking-tight sm:text-3xl">A smaller scope.<br />A stronger demonstration.</h3><p className="mt-4 text-sm leading-6 text-muted-foreground">Fixed mock output for interface testing. This plan is not generated from, or tailored to, your input.</p></div>
        <section aria-labelledby="submitted-heading" className="rounded-lg border bg-muted/40 p-4"><h4 id="submitted-heading" className="text-sm font-medium">Your submitted brief</h4><p className="mt-2 max-h-48 overflow-y-auto text-sm leading-6 whitespace-pre-wrap [overflow-wrap:anywhere]">{brief}</p></section>
        <section aria-labelledby="priorities-heading"><div className="mb-5 flex items-center justify-between gap-3"><h4 id="priorities-heading" className="text-sm font-semibold">Recommended priorities</h4><span className="text-sm text-muted-foreground">Sample plan</span></div><ol className="divide-y">{priorities.map(item => <li key={item.number} className="flex gap-4 py-5 first:pt-0 last:pb-0"><span className="pt-0.5 font-mono text-sm text-muted-foreground">{item.number}</span><div><h5 className="text-sm font-medium">{item.title}</h5><p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p></div></li>)}</ol></section>
        <section aria-labelledby="next-heading" className="border-l-2 border-primary pl-5"><h4 id="next-heading" className="flex items-center gap-2 text-sm font-semibold">The next move <ArrowUpRight aria-hidden="true" className="size-4" /></h4><p className="mt-2 text-sm leading-6 text-muted-foreground">Write the happy-path demo script together. Assign one owner to each step, then agree on the API contract before implementation.</p></section>
      </div>
      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t bg-muted/20 px-5 py-4 sm:px-8"><span className="text-sm text-muted-foreground">Human review before any action.</span><Button variant="outline" className="h-11" onClick={onReset}><RotateCcw aria-hidden="true" />Reset preview</Button></div>
    </article>
  );
}
