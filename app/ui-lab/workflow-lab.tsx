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
  { title: "Understand the brief", detail: "Clarify the outcome and constraints." },
  { title: "Shape the approach", detail: "A focused, end-to-end user journey." },
  { title: "Prepare the handoff", detail: "Recommendations ready for review." },
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
    <div className="lab-workspace" data-state={state}>
        <section aria-labelledby="brief-heading" className={cn("lab-panel", "lab-composerPanel")}>
          <div className="lab-sectionHeader"><h2 id="brief-heading"><span className="lab-sectionIndex">01</span> Request</h2><Badge variant="secondary" className="lab-mockBadge">Mock mode</Badge></div>
          <form onSubmit={startRun}>
            <label htmlFor="agent-brief" className="lab-fieldLabel">What would you like to accomplish?</label>
            <p id="brief-help" className="lab-fieldHelp">Start with a goal and constraints. Every brief returns the same sample plan.</p>
            <textarea ref={composerRef} id="agent-brief" value={brief} onChange={event => setBrief(event.target.value.slice(0, 2000))} disabled={running} required maxLength={2000} aria-describedby="brief-help brief-count" placeholder="What would a useful outcome look like?" className="lab-textarea" />
            <div className="lab-composerMeta"><Button type="button" variant="ghost" disabled={running} onClick={() => setBrief(example)} className="lab-exampleButton">Use example brief <ArrowRight aria-hidden="true" /></Button><span id="brief-count" className="lab-characterCount">{brief.length}/2000</span></div>
            <label className="lab-simulationToggle"><input type="checkbox" checked={simulateError} disabled={running} onChange={event => setSimulateError(event.target.checked)} />Simulate a failure to test recovery</label>
            <div className="lab-controls"><Button type="submit" disabled={running || !brief.trim()} className="lab-runButton">{running ? <LoaderCircle aria-hidden="true" className="motion-safe:animate-spin" /> : <ArrowRight aria-hidden="true" />}{running ? "Working on your brief" : "Run mock workflow"}</Button>{running && <Button type="button" ref={cancelRef} variant="outline" onClick={() => reset(true)} className="lab-controlButton"><Square aria-hidden="true" />Cancel</Button>}</div>
          </form>
          <p className="lab-privacyNote"><ShieldCheck aria-hidden="true" className="size-3.5 shrink-0" />Your brief stays in this browser tab.</p>
        </section>
      <div className="lab-panel lab-activityPanel">
        <section aria-labelledby="progress-heading" className="lab-progressPanel">
          <div className="lab-sectionHeader"><h2 id="progress-heading"><span className="lab-sectionIndex">02</span> Execution trace</h2><span className="lab-progressCount">{state === "success" ? "Complete · 3 / 3" : state === "error" ? "Interrupted" : running ? `In progress · ${step} / 3` : "Ready to begin"}</span></div>
          <ol className="lab-stepList">
            {steps.map((item, index) => {
              const done = state === "success" || ((running || state === "error") && index < step && !(state === "error" && index === 2));
              const active = running && index === step;
              const failed = state === "error" && index === 2;
              return <li key={item.title} data-active={active} data-done={done} data-failed={failed} aria-current={active ? "step" : undefined}><div className="lab-stageTop"><span className={cn("lab-stepIcon", done && "lab-stepDone", active && "lab-stepActive", failed && "lab-stepFailed")} aria-hidden="true">{failed ? <CircleAlert className="size-3.5" /> : done ? <Check className="size-3.5" /> : active ? <LoaderCircle className="size-3.5 motion-safe:animate-spin" /> : <Circle className="size-2" />}</span><span className="lab-stageLabel">{["INTENT", "PLAN", "RESULT"][index]}</span><span className="lab-stageState">{done ? "Done" : active ? "Active" : failed ? "Failed" : "Pending"}</span></div><div className="lab-stageDescription"><p className="lab-stepTitle">{item.title}</p><p className="lab-stepDetail">{item.detail}</p></div></li>;
            })}
          </ol>
          <p role="status" aria-live="polite" aria-atomic="true" className="lab-statusMessage">{message}</p>
        </section>
      <section aria-labelledby="result-heading" className="lab-resultPanel">
        <div className={cn("lab-sectionHeader", "lab-resultHeader")}><h2 ref={resultRef} tabIndex={-1} id="result-heading"><span className="lab-sectionIndex">03</span> Review the outcome</h2><Badge className="lab-resultBadge" variant={state === "error" ? "destructive" : "outline"}>{state === "success" && !stale && <Check aria-hidden="true" />}{stale ? "Previous run" : state === "success" ? "Mock result · Ready" : state === "error" ? "Mock error" : "Result preview"}</Badge></div>
        {stale && <p role="status" className="lab-staleNotice">Previous run: your brief has changed. Run the workflow again to associate a new mock result with this brief.</p>}
        <div aria-busy={running} className="lab-resultBody">
          {state === "empty" && <div className="lab-emptyLayout">
            <p className="lab-documentLabel">FROM A FIRST THOUGHT TO A NEXT MOVE</p>
            <div className="lab-emptyMessage"><EmptyState icon={<FileText />} title="Your next move, made clear." description="One focused brief. A visible path through the work. An outcome you can put into action." /></div>
            <dl className="lab-outputOutline"><div><dt>01 / A focused brief</dt><dd>The goal, kept in view.</dd></div><div><dt>02 / Clear priorities</dt><dd>A smaller, ordered scope.</dd></div><div><dt>03 / A practical handoff</dt><dd>One useful next move.</dd></div></dl>
            <p className="lab-emptyFootnote">Run the local simulation to explore a fixed sample outcome.</p>
          </div>}
          {running && <div className="lab-runningPreview"><p className="lab-documentLabel">LOCAL SIMULATION / IN PROGRESS</p><h3>Turning the brief into a plan.</h3><p className="lab-runningDescription">{steps[step].detail} Simulated step {step + 1} of 3. No external tools or models are being called.</p><progress className="lab-progressBar" max={3} value={step} aria-label="Completed mock stages" /><div className="lab-skeleton" aria-hidden="true">{["w-3/4", "w-full", "w-5/6"].map(width => <div key={width} className={width} />)}</div><p className="lab-emptyFootnote">Your brief stays in view. Cancel whenever you need.</p></div>}
          {state === "error" && <div className="lab-errorLayout"><ErrorState title="A deliberate bump in the road." description="This failure was simulated. Retry clears the failure setting and immediately starts a new mock run using your current brief." action={<Button variant="outline" disabled={!brief.trim()} className="lab-controlButton" onClick={() => { setSimulateError(false); run(false); }}><RotateCcw aria-hidden="true" />Retry mock workflow</Button>} /></div>}
          {state === "success" && <ResultPreview brief={submittedBrief} onReset={() => reset()} />}
        </div>
      </section>
      </div>
    </div>
  );
}
