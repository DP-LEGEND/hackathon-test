"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Check, Circle, CircleAlert, FileText, LoaderCircle, RotateCcw, ShieldCheck, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { cn } from "@/lib/utils";
import { ResultPreview } from "./result-preview";

type RunState = "empty" | "running" | "success" | "error";
const example = "Help our four-person team turn a hackathon idea into a focused, demo-ready plan.";
const steps = [
  { title: "Understand the brief", detail: "Identify the intended outcome and constraints." },
  { title: "Shape the approach", detail: "Prioritise the smallest complete user journey." },
  { title: "Prepare the handoff", detail: "Organise recommendations for human review." },
];

export function WorkflowLab() {
  const [brief, setBrief] = useState("");
  const [submittedBrief, setSubmittedBrief] = useState("");
  const [state, setState] = useState<RunState>("empty");
  const [step, setStep] = useState(0);
  const [simulateError, setSimulateError] = useState(false);
  const [message, setMessage] = useState("Ready when you are. Add a brief to begin.");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const generation = useRef(0);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const resultRef = useRef<HTMLHeadingElement>(null);
  const focusTarget = useRef<"composer" | "cancel" | "result" | null>(null);
  const running = state === "running";
  const stale = state === "success" && brief.trim() !== submittedBrief;

  function clearTimer() {
    generation.current += 1;
    if (timer.current !== null) clearInterval(timer.current);
    timer.current = null;
  }

  useEffect(() => () => { if (timer.current !== null) clearInterval(timer.current); }, []);

  useEffect(() => {
    const target = focusTarget.current;
    focusTarget.current = null;
    if (target === "composer") composerRef.current?.focus();
    if (target === "cancel") cancelRef.current?.focus();
    if (target === "result") resultRef.current?.focus();
  }, [state]);

  function startRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    run(simulateError);
  }

  function run(fail: boolean) {
    if (timer.current !== null || !brief.trim() || brief.length > 2000) return;
    const runGeneration = ++generation.current;
    focusTarget.current = "cancel";
    setSubmittedBrief(brief.trim());
    setState("running");
    setStep(0);
    setMessage("Mock run started. Step 1 of 3: Understand the brief.");
    let current = 0;
    timer.current = setInterval(() => {
      if (generation.current !== runGeneration) return;
      current += 1;
      if (current === 3) {
        clearTimer();
        setStep(3);
        focusTarget.current = "result";
        setState(fail ? "error" : "success");
        setMessage(fail ? "Simulated failure. Retry mock workflow clears the failure setting and starts a new run." : "Mock run complete. Your sample plan is ready for review.");
      } else {
        setStep(current);
        setMessage(`Step ${current + 1} of 3: ${steps[current].title}.`);
      }
    }, 1100);
  }

  function reset(cancelled = false) {
    clearTimer();
    focusTarget.current = "composer";
    setState("empty");
    setStep(0);
    setMessage(cancelled ? "Run cancelled. Your brief is preserved; you can run it again." : "Preview reset. Ready for another run.");
  }

  return (
    <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] [&_.text-muted-foreground]:text-foreground/75">
        <section aria-labelledby="brief-heading" className="rounded-xl border bg-card p-5 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-3"><h2 id="brief-heading" className="text-base font-semibold">01 <span className="ml-2">Define the task</span></h2><Badge variant="secondary">Mock mode</Badge></div>
          <form onSubmit={startRun}>
            <label htmlFor="agent-brief" className="text-sm font-medium">What would you like to accomplish?</label>
            <p id="brief-help" className="mt-2 text-sm leading-5 text-muted-foreground">Describe a goal and any constraints. This prototype returns a fixed sample plan for every brief.</p>
            <textarea ref={composerRef} id="agent-brief" value={brief} onChange={event => setBrief(event.target.value.slice(0, 2000))} disabled={running} required maxLength={2000} aria-describedby="brief-help brief-count" placeholder="Start with an outcome, not a list of tools…" className="mt-4 min-h-28 w-full resize-y rounded-lg border bg-background p-4 text-sm leading-6 placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60" />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2"><Button type="button" variant="ghost" disabled={running} onClick={() => setBrief(example)} className="min-h-11 px-0 text-sm">Use example brief <ArrowRight aria-hidden="true" /></Button><span id="brief-count" className="font-mono text-sm text-muted-foreground">{brief.length}/2000</span></div>
            <div className="my-3 border-t pt-3"><label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm text-muted-foreground"><input type="checkbox" checked={simulateError} disabled={running} onChange={event => setSimulateError(event.target.checked)} className="size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring" />Simulate a failure to test recovery</label></div>
            <div className="flex flex-wrap gap-3"><Button type="submit" disabled={running || !brief.trim()} className="h-11 flex-1 px-5">{running ? <LoaderCircle aria-hidden="true" className="motion-safe:animate-spin" /> : <ArrowRight aria-hidden="true" />}{running ? "Working on your brief" : "Run mock workflow"}</Button>{running && <Button type="button" ref={cancelRef} variant="outline" onClick={() => reset(true)} className="h-11"><Square aria-hidden="true" />Cancel</Button>}</div>
          </form>
          <p className="mt-4 flex items-center gap-2 text-sm text-muted-foreground"><ShieldCheck aria-hidden="true" className="size-3.5 shrink-0" />Your brief stays in this browser tab.</p>
        </section>
        <section aria-labelledby="progress-heading" className="rounded-xl border bg-card p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3"><h2 id="progress-heading" className="text-base font-semibold">02 <span className="ml-2">Follow the work</span></h2><span className="font-mono text-sm text-muted-foreground">{state === "success" ? "3 / 3" : state === "error" ? "Failed" : running ? `${step} / 3` : "Standby"}</span></div>
          <ol className="mt-4 space-y-4">
            {steps.map((item, index) => {
              const done = state === "success" || ((running || state === "error") && index < step && !(state === "error" && index === 2));
              const active = running && index === step;
              const failed = state === "error" && index === 2;
              return <li key={item.title} className="flex gap-4"><span className={cn("mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border", done && "border-primary bg-primary text-primary-foreground", active && "border-foreground", failed && "border-destructive text-destructive")} aria-hidden="true">{failed ? <CircleAlert className="size-3.5" /> : done ? <Check className="size-3.5" /> : active ? <LoaderCircle className="size-3.5 motion-safe:animate-spin" /> : <Circle className="size-2 text-muted-foreground" />}</span><div><p className="text-sm font-medium">{item.title}<span className="sr-only"> — {done ? "complete" : active ? "in progress" : state === "error" && index === 2 ? "failed" : "pending"}</span></p><p className="mt-1 hidden text-sm leading-5 text-muted-foreground sm:block">{item.detail}</p></div></li>;
            })}
          </ol>
          <p role="status" aria-live="polite" aria-atomic="true" className="mt-4 border-t pt-4 text-sm leading-5 text-muted-foreground">{message}</p>
        </section>
      <section aria-labelledby="result-heading" className="flex min-w-0 flex-col overflow-hidden rounded-xl border bg-card lg:col-span-2">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4 sm:px-7"><h2 ref={resultRef} tabIndex={-1} id="result-heading" className="rounded-sm text-base font-semibold focus:outline-2 focus:outline-offset-4 focus:outline-ring">03 <span className="ml-2">Review the outcome</span></h2><Badge variant={state === "error" ? "destructive" : "outline"}>{state === "success" && !stale && <Check aria-hidden="true" />}{stale ? "Previous run" : state === "success" ? "Mock result · Ready" : state === "error" ? "Mock error" : "Result preview"}</Badge></div>
        {stale && <p role="status" className="border-b bg-muted/40 px-5 py-4 text-sm sm:px-7">Previous run: your brief has changed. Run the workflow again to associate a new mock result with this brief.</p>}
        <div aria-busy={running} className="flex flex-1 flex-col">
          {state === "empty" && <div className="[&>div]:py-8"><EmptyState icon={<FileText />} title="A little clarity starts here." description="Run a mock workflow to see a structured brief, priorities, and a practical handoff. Your result will appear here." /></div>}
          {running && <div className="flex flex-1 flex-col justify-center px-7 py-20"><LoaderCircle aria-hidden="true" className="mb-5 size-6 motion-safe:animate-spin" /><h3 className="text-xl font-medium tracking-tight">Turning the brief into a plan.</h3><p className="mt-3 text-sm leading-6 text-muted-foreground">Simulated step {step + 1} of 3. No external tools or models are being called.</p><div className="mt-8 space-y-4" aria-hidden="true">{["w-3/4", "w-full", "w-5/6"].map(width => <div key={width} className={cn("h-3 rounded bg-muted motion-safe:animate-pulse", width)} />)}</div></div>}
          {state === "error" && <div className="flex flex-1 items-center justify-center"><ErrorState title="A deliberate bump in the road." description="This failure was simulated. Retry clears the failure setting and immediately starts a new mock run using your current brief." action={<Button variant="outline" disabled={!brief.trim()} className="h-11" onClick={() => { setSimulateError(false); run(false); }}><RotateCcw aria-hidden="true" />Retry mock workflow</Button>} /></div>}
          {state === "success" && <ResultPreview brief={submittedBrief} onReset={() => reset()} />}
        </div>
      </section>
    </div>
  );
}
