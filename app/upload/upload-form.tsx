"use client";

// The /upload flow: choose a clip, optional settings, send it to the pipeline, then open the new
// swing in /ghost (?swing=<id>). One request at a time; the service also runs one clip at a time.
// The request itself is process-clip.ts.

import { useEffect, useEffectEvent, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, CircleAlert, Hourglass, ListVideo } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR } from "../ghost/colours";
import { ClipDrop } from "./clip-drop";
import { ClipSettingsPanel } from "./clip-settings";
import {
  AUTO_SETTINGS,
  checkClip,
  processClip,
  type ClipSettings,
  type ProcessFailure,
  type ProcessJob,
  type Slowdown,
} from "./process-clip";
import { ProgressPanel } from "./progress-panel";

type Phase =
  | { kind: "idle"; notice: string | null }
  | { kind: "working"; startedAt: number; uploadedAt: number | null; progress: number | null }
  | { kind: "failed"; failure: ProcessFailure; slowdown: Slowdown }
  | { kind: "done"; href: string };

const IDLE: Phase = { kind: "idle", notice: null };
const START_COMMAND = "python -m uvicorn pipeline.server:app --app-dir services --port 8000";

const TIPS = [
  "Normal video at 60 fps works best",
  "Whole body in frame",
  "One clear swing per clip",
  "Slow motion? Set Slowdown below",
];

/**
 * Every visit to /upload gets a new form. Next keeps a page alive but hidden after you leave it
 * (Activity, Cache Components), so leaving bumps the key: the old form unmounts, its cleanup
 * aborts any upload, and coming back mounts a fresh form, never an old progress or "done" state.
 */
export function UploadForm() {
  const [visit, setVisit] = useState(0);
  useLayoutEffect(() => () => setVisit((n) => n + 1), []);
  return <UploadFlow key={visit} />;
}

function UploadFlow() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [clipError, setClipError] = useState<string | null>(null);
  const [settings, setSettings] = useState<ClipSettings>(AUTO_SETTINGS);
  const [phase, setPhase] = useState<Phase>(IDLE);
  const [dragging, setDragging] = useState(false);

  const job = useRef<ProcessJob | null>(null);
  const focusTarget = useRef<"progress" | "submit" | null>(null);
  const progressRef = useRef<HTMLHeadingElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);

  const busy = phase.kind === "working" || phase.kind === "done";

  // Leaving the page (hidden or unmounted) abandons an upload in progress: abort the request and
  // ignore its answer (send() checks the job is still current). The progress panel's timer
  // stops with it, as that panel unmounts too.
  useLayoutEffect(
    () => () => {
      const abandoned = job.current;
      job.current = null;
      abandoned?.cancel();
    },
    [],
  );

  useEffect(() => {
    const target = focusTarget.current;
    focusTarget.current = null;
    if (target === "progress") progressRef.current?.focus();
    if (target === "submit") submitRef.current?.focus();
  }, [phase.kind]);

  // A rejected file also clears the clip chosen before it, so Build can never send a file the
  // user just tried to replace. Build stays disabled until a valid clip is chosen.
  function pick(next: File) {
    if (busy) return;
    const problem = checkClip(next);
    setClipError(problem);
    setFile(problem ? null : next);
    setPhase(IDLE);
  }

  function clear() {
    setFile(null);
    setClipError(null);
    setPhase(IDLE);
  }

  // A video dropped anywhere on the page becomes the clip (dropped elsewhere, the browser would
  // open it and leave the page). Only file drags count, not dragged text.
  const onDropped = useEffectEvent((next: File) => pick(next));
  const isBusy = useEffectEvent(() => busy);
  useEffect(() => {
    let depth = 0;
    const hasFiles = (event: DragEvent) => event.dataTransfer?.types.includes("Files") ?? false;
    const enter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth += 1;
      setDragging(true);
    };
    const over = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = isBusy() ? "none" : "copy";
    };
    const leave = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth = Math.max(0, depth - 1);
      if (depth === 0) setDragging(false);
    };
    const drop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      setDragging(false);
      const next = event.dataTransfer?.files[0];
      if (next) onDropped(next);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragover", over);
    window.addEventListener("dragleave", leave);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragover", over);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("drop", drop);
    };
  }, []);

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || job.current) return;
    const sent = settings;
    focusTarget.current = "progress";
    setPhase({ kind: "working", startedAt: Date.now(), uploadedAt: null, progress: 0 });
    router.prefetch("/ghost");

    const current = processClip(file, sent, {
      progress: (fraction) =>
        setPhase((p) => (p.kind === "working" && p.uploadedAt === null ? { ...p, progress: fraction } : p)),
      uploaded: () => {
        const at = Date.now();
        setPhase((p) => (p.kind === "working" ? { ...p, uploadedAt: at, progress: 1 } : p));
      },
    });
    job.current = current;
    const outcome = await current.result;
    if (job.current !== current) return; // the page was left: this upload was abandoned
    job.current = null;

    if (outcome.ok) {
      const href = `/ghost?swing=${encodeURIComponent(outcome.swingId)}`;
      setPhase({ kind: "done", href });
      router.push(href);
      return;
    }
    focusTarget.current = "submit";
    if ("cancelled" in outcome) {
      setPhase({
        kind: "idle",
        notice: outcome.uploaded
          ? "Stopped waiting. The service may still finish that clip; until it does, a new upload will say a clip is already processing."
          : "Upload cancelled.",
      });
      return;
    }
    setPhase({ kind: "failed", failure: outcome.failure, slowdown: sent.slowdown });
  }

  return (
    <form onSubmit={send} noValidate className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <ClipDrop file={file} dragging={dragging} disabled={busy} error={clipError} onPick={pick} onClear={clear} />
        <ul aria-label="Filming tips" className="grid gap-x-6 gap-y-1.5 text-sm text-muted-foreground sm:grid-cols-2">
          {TIPS.map((tip) => (
            <li key={tip} className="flex items-center gap-2">
              <span aria-hidden className="size-1 shrink-0 rounded-full bg-muted-foreground" />
              {tip}
            </li>
          ))}
        </ul>
      </div>

      <ClipSettingsPanel value={settings} onChange={setSettings} disabled={busy} />

      {phase.kind === "working" ? (
        <ProgressPanel
          startedAt={phase.startedAt}
          uploadedAt={phase.uploadedAt}
          progress={phase.progress}
          onCancel={() => job.current?.cancel()}
          headingRef={progressRef}
        />
      ) : phase.kind === "done" ? (
        <Ready href={phase.href} />
      ) : (
        <div className="flex flex-col gap-4">
          {phase.kind === "failed" && <Failure failure={phase.failure} slowdown={phase.slowdown} />}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <Button
              ref={submitRef}
              type="submit"
              size="lg"
              className="h-11 px-5 text-base"
              disabled={!file}
              aria-describedby="send-hint"
            >
              {phase.kind === "failed" ? "Try again" : "Build my ghost"}
              <ArrowRight data-icon="inline-end" />
            </Button>
            <p id="send-hint" className="text-sm text-muted-foreground">
              {file ? "Processing can take a minute." : "Choose a video to start."}
            </p>
          </div>
          {phase.kind === "idle" && phase.notice && (
            <p role="status" className="text-sm text-muted-foreground">
              {phase.notice}
            </p>
          )}
        </div>
      )}
    </form>
  );
}

function Ready({ href }: { href: string }) {
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-card p-4 sm:p-5"
      style={{ borderColor: `color-mix(in oklch, ${GHOST_COLOUR} 45%, transparent)` }}
    >
      <p className="flex items-center gap-2 text-base font-medium">
        <Check aria-hidden className="size-5" style={{ color: GHOST_COLOUR }} />
        Your ghost is ready.
      </p>
      <Link href={href} className={buttonVariants()}>
        Open it in Ghost
        <ArrowRight data-icon="inline-end" aria-hidden />
      </Link>
    </div>
  );
}

type FailureCopy = {
  title: string;
  message?: string;
  hint?: string;
  command?: string;
  swingList?: boolean;
  /** Not an error: the service is probably still working on the clip. */
  waiting?: boolean;
};

function describe(failure: ProcessFailure, slowdown: Slowdown): FailureCopy {
  switch (failure.kind) {
    case "busy":
      return {
        title: "A clip is already processing",
        message: "The service works on one clip at a time. Wait for it to finish, then try again.",
      };
    case "too-large":
      return { title: "Clip too large", message: failure.message, hint: "Trim the clip to just the swing, then try again." };
    case "offline":
      return {
        title: "The Ghost service isn’t running",
        message: failure.message,
        hint: "Start it from the repo folder, with the Python environment active, then try again:",
        command: START_COMMAND,
      };
    case "proxy-timeout":
      return {
        title: "Still processing, but this page stopped waiting",
        message:
          "The web proxy stopped waiting before the service finished this clip. The Python service keeps going, so your swing should appear in Ghost’s swing list when it’s done.",
        swingList: true,
        waiting: true,
      };
    case "no-route":
      return {
        title: "This service can’t take uploads yet",
        message: "The Python service answered that it has no POST /process route.",
        hint: "Restart it from a version with the upload API (PR #41), then try again.",
      };
    case "network":
      return {
        title: "Couldn’t reach Ghost",
        message: "The upload got no answer from the web server. Check it’s still running, then try again.",
      };
    case "failed":
      return {
        title: "Couldn’t build your ghost",
        message: failure.message,
        // 503 is the service's own setup (pose model, ffmpeg); the clip's timing won't fix that.
        hint: failure.status === 503 ? undefined : slowdownHint(slowdown),
      };
  }
}

function slowdownHint(slowdown: Slowdown): string {
  return slowdown === "auto"
    ? "Filmed in slow motion? Set Slowdown to match the clip (4× or 8×), then try again."
    : "Check Slowdown matches the clip: 1× for normal video, 4× or 8× for slow motion. Or set it back to Auto.";
}

function Failure({ failure, slowdown }: { failure: ProcessFailure; slowdown: Slowdown }) {
  const copy = describe(failure, slowdown);
  const Icon = copy.waiting ? Hourglass : CircleAlert;
  return (
    <div
      role={copy.waiting ? "status" : "alert"}
      className={cn("flex gap-3 rounded-2xl border bg-card p-4 sm:p-5", !copy.waiting && "border-destructive/40")}
    >
      <Icon aria-hidden className={cn("mt-0.5 size-5 shrink-0", copy.waiting ? "text-muted-foreground" : "text-destructive")} />
      <div className="flex min-w-0 flex-col gap-1.5">
        <h2 className="text-base font-medium">{copy.title}</h2>
        {copy.message && <p className="text-sm break-words">{copy.message}</p>}
        {copy.hint && <p className="text-sm text-pretty text-muted-foreground">{copy.hint}</p>}
        {copy.command && (
          <code className="w-fit max-w-full rounded-md bg-muted px-2 py-1 font-mono text-xs break-all text-foreground">
            {copy.command}
          </code>
        )}
        {copy.swingList && (
          <Link href="/ghost" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-1 w-fit")}>
            <ListVideo data-icon="inline-start" aria-hidden />
            Open the swing list
          </Link>
        )}
      </div>
    </div>
  );
}
