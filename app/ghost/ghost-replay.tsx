"use client";

// Interactive 3D swing replay: your swing (orange) and the ghost (cyan), aligned at contact.
// Owns loading and the playback clock; the three.js scene is loaded on demand.

import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Columns2, Crosshair, Layers, Pause, Play, RotateCcw, Turtle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import type { SkeletonScene } from "./skeleton-scene";
import { buildTimeline, frameIndexAt, loadSwing, samplePose, type LoadedSwing, type Timeline } from "./swing";

const SOURCES = {
  you: "/swings/swing_2116_bh_stereo.json",
  // MOCK: a copy of your swing until the coach's fix produces a real ghost.
  ghost: "/swings/ghost_2116_bh_stereo.json",
} as const;
const GHOST_IS_MOCK = true;

const SLOW_MO = 0.25;
const THUMB_PX = 16; // native range thumb width, used to line the contact tick up with it

type ReplayData = { you: LoadedSwing; ghost: LoadedSwing; timeline: Timeline };
type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: ReplayData };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function fetchSwing(url: string, signal: AbortSignal): Promise<LoadedSwing> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Couldn't load ${url} (HTTP ${response.status}).`);
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new Error(`${url} isn't valid JSON. NaN or Infinity values aren't allowed.`);
  }
  try {
    return loadSwing(json);
  } catch (error) {
    throw new Error(`${url} doesn't match the Swing format: ${errorMessage(error)}.`);
  }
}

function formatTau(tau: number, step: number): string {
  if (Math.abs(tau) < step / 2) return "Contact";
  const ms = Math.round(Math.abs(tau) * 1000);
  return tau < 0 ? `${ms} ms before contact` : `${ms} ms after contact`;
}

export function GhostReplay() {
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [tau, setTau] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [slowMo, setSlowMo] = useState(false);
  const [sideBySide, setSideBySide] = useState(false);

  // The animation loop reads these refs so it never restarts on a state change.
  const viewportRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<SkeletonScene | null>(null);
  const tauRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const sideBySideRef = useRef(false);

  const data = load.status === "ready" ? load.data : null;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchSwing(SOURCES.you, controller.signal), fetchSwing(SOURCES.ghost, controller.signal)])
      .then(([you, ghost]) => {
        const timeline = buildTimeline([you, ghost]);
        // Respect reduced motion: start paused on the contact frame instead of autoplaying.
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        tauRef.current = reduceMotion ? 0 : timeline.start;
        playingRef.current = !reduceMotion;
        setTau(tauRef.current);
        setPlaying(!reduceMotion);
        setLoad({ status: "ready", data: { you, ghost, timeline } });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", message: errorMessage(error) });
      });
    return () => controller.abort();
  }, [attempt]);

  useEffect(() => {
    const container = viewportRef.current;
    if (!data || !container) return;
    let cancelled = false;
    let frameId = 0;
    let scene: SkeletonScene | null = null;

    import("./skeleton-scene")
      .then(({ SkeletonScene }) => {
        if (cancelled) return;
        const s = new SkeletonScene(container, { you: data.you.floorY, ghost: data.ghost.floorY });
        scene = s;
        sceneRef.current = s;
        s.setSideBySide(sideBySideRef.current);

        const { start, end } = data.timeline;
        const span = end - start;
        let last = performance.now();
        let drawnTau = Number.NaN;
        const tick = (now: number) => {
          const dt = Math.min((now - last) / 1000, 0.1);
          last = now;
          if (playingRef.current && span > 0) {
            let next = tauRef.current + dt * speedRef.current;
            if (next > end) next = start + ((next - end) % span);
            tauRef.current = next;
            setTau(next);
          }
          if (tauRef.current !== drawnTau) {
            drawnTau = tauRef.current;
            s.setPoses(samplePose(data.you, drawnTau), samplePose(data.ghost, drawnTau));
          }
          s.render();
          frameId = requestAnimationFrame(tick);
        };
        frameId = requestAnimationFrame(tick);
      })
      .catch((error: unknown) => {
        if (!cancelled) setSceneError(`The 3D view couldn't start (${errorMessage(error)}). WebGL may be turned off.`);
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(frameId);
      scene?.dispose();
      sceneRef.current = null;
    };
  }, [data]);

  function setPlayback(next: boolean) {
    playingRef.current = next;
    setPlaying(next);
  }

  function toggleSlowMo() {
    const next = !slowMo;
    speedRef.current = next ? SLOW_MO : 1;
    setSlowMo(next);
  }

  function seek(next: number) {
    tauRef.current = next;
    setTau(next);
    setPlayback(false);
  }

  function onScrub(event: ChangeEvent<HTMLInputElement>) {
    seek(Number(event.target.value));
  }

  function toggleSideBySide() {
    const next = !sideBySide;
    sideBySideRef.current = next;
    sceneRef.current?.setSideBySide(next);
    setSideBySide(next);
  }

  function retry() {
    setLoad({ status: "loading" });
    setSceneError(null);
    setAttempt((n) => n + 1);
  }

  const timeline = data?.timeline;
  const span = timeline ? timeline.end - timeline.start : 0;
  const contactPct = timeline && span > 0 ? ((0 - timeline.start) / span) * 100 : 0;
  const youFrame = data ? frameIndexAt(data.you, tau) : 0;
  const ghostFrame = data ? frameIndexAt(data.ghost, tau) : 0;
  const timeLabel = timeline ? formatTau(tau, timeline.step) : "";
  const error = load.status === "error" ? load.message : sceneError;

  return (
    <section aria-label="Swing replay" className="flex flex-col gap-4">
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <SwingLegend colour={YOU_COLOUR} name="You" swing={data?.you} />
        <SwingLegend
          colour={GHOST_COLOUR}
          name="Ghost"
          swing={data?.ghost}
          mockNote={GHOST_IS_MOCK ? "Copy of your swing until the coach's fix is wired in." : undefined}
        />
      </div>

      <div className="relative h-[min(68vh,680px)] min-h-80 overflow-hidden rounded-xl border bg-card">
        <div
          ref={viewportRef}
          role="img"
          aria-label="3D replay on a squash court: your swing in orange and the ghost in cyan. Drag to rotate, scroll to zoom."
          className="absolute inset-0 cursor-grab active:cursor-grabbing"
        />
        {load.status === "loading" && (
          <p className="absolute inset-0 grid place-items-center text-sm text-muted-foreground" role="status">
            Loading swings…
          </p>
        )}
        {error && (
          <div
            role="alert"
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-card p-6 text-center"
          >
            <p className="max-w-md text-sm text-foreground">{error}</p>
            <Button variant="outline" onClick={retry}>
              <RotateCcw data-icon="inline-start" />
              Try again
            </Button>
          </div>
        )}
        {data && !error && (
          <>
            <p className="pointer-events-none absolute top-3 right-3 left-3 text-right text-xs text-muted-foreground">
              Court 6.40 × 9.75 m · 1 m grid · front wall at the far end · player shown at the T
            </p>
            <p className="pointer-events-none absolute bottom-3 left-3 text-xs text-muted-foreground">
              Drag to rotate · Scroll to zoom · Right-drag to pan
            </p>
          </>
        )}
      </div>

      <div className="flex flex-col gap-3 rounded-xl border bg-card p-3 sm:p-4">
        <div className="relative pt-4">
          {timeline && (
            <span
              aria-hidden
              className="pointer-events-none absolute top-0 flex -translate-x-1/2 flex-col items-center text-[0.65rem] leading-none text-muted-foreground"
              style={{ left: `calc(${contactPct}% + ${(0.5 - contactPct / 100) * THUMB_PX}px)` }}
            >
              contact
              <span className="mt-0.5 h-2 w-px bg-muted-foreground" />
            </span>
          )}
          <label htmlFor="ghost-scrub" className="sr-only">
            Swing time
          </label>
          <input
            id="ghost-scrub"
            type="range"
            className="w-full accent-foreground disabled:opacity-50"
            min={timeline?.start ?? 0}
            max={timeline?.end ?? 1}
            step={timeline?.step ?? 0.01}
            value={tau}
            onChange={onScrub}
            disabled={!data}
            aria-valuetext={`${timeLabel}, your frame ${youFrame}, ghost frame ${ghostFrame}`}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setPlayback(!playing)} disabled={!data} className="min-w-24">
            {playing ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
            {playing ? "Pause" : "Play"}
          </Button>
          <Button variant={slowMo ? "secondary" : "outline"} onClick={toggleSlowMo} aria-pressed={slowMo} disabled={!data}>
            <Turtle data-icon="inline-start" />
            0.25× slow-mo
          </Button>
          <Button variant="outline" onClick={() => seek(0)} disabled={!data}>
            <Crosshair data-icon="inline-start" />
            Contact
          </Button>

          <p className="mx-auto px-2 font-mono text-xs text-muted-foreground tabular-nums">
            <span className="text-foreground">{timeLabel || "–"}</span>
            {data && (
              <>
                {" · "}
                <span style={{ color: YOU_COLOUR }}>you f{youFrame}</span>
                {" · "}
                <span style={{ color: GHOST_COLOUR }}>ghost f{ghostFrame}</span>
                {" · "}
                {slowMo ? `${SLOW_MO}×` : "1×"}
              </>
            )}
          </p>

          <Button variant="outline" onClick={toggleSideBySide} aria-pressed={sideBySide} disabled={!data}>
            {sideBySide ? <Layers data-icon="inline-start" /> : <Columns2 data-icon="inline-start" />}
            {sideBySide ? "Overlay" : "Side by side"}
          </Button>
          <Button variant="ghost" onClick={() => sceneRef.current?.resetView()} disabled={!data}>
            <RotateCcw data-icon="inline-start" />
            Reset view
          </Button>
        </div>
      </div>
    </section>
  );
}

function SwingLegend({
  colour,
  name,
  swing,
  mockNote,
}: {
  colour: string;
  name: string;
  swing: LoadedSwing | undefined;
  mockNote?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border bg-card px-3 py-2.5">
      <span aria-hidden className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colour }} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="flex items-center gap-2 font-medium">
          {name}
          {mockNote && (
            <Badge variant="outline" className="border-amber-400/50 text-amber-300">
              MOCK
            </Badge>
          )}
        </p>
        <div className="text-xs text-muted-foreground">
          {swing ? (
            <>
              <span className="break-all">{swing.swing.id}</span> · {swing.swing.fps} fps · {swing.swing.frames.length} frames ·
              contact f{swing.contactFrame}{" "}
              <span className={cn(swing.contactSource === "fastest-wrist" && "text-amber-300")}>
                ({swing.contactSource === "file" ? "from file" : "fallback: fastest wrist"})
              </span>
              {swing.flippedFromYDown && " · y-down input shown y-up"}
            </>
          ) : (
            "Loading…"
          )}
          {mockNote && <span className="block">{mockNote}</span>}
        </div>
      </div>
    </div>
  );
}
