"use client";

// Interactive 3D swing replay: your swing (orange) and the ghost (cyan) aligned at contact,
// both PREDICTED ball paths on the court, the coach's caption and a fix picker.
// Owns loading and the playback clock; the three.js scene is loaded on demand.
// Data: real output of services/ (physics.compare and coach.agent), see public/swings/README.md.

import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import {
  Columns2,
  Crosshair,
  Grid3x3,
  Layers,
  Pause,
  PersonStanding,
  Play,
  RotateCcw,
  Turtle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CoachCaptionBar, type CoachState } from "./coach-caption";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import {
  OUTCOME_WORDS,
  fixName,
  formatValue,
  parseCoach,
  parseCompare,
  type BallPath,
  type CompareResult,
} from "./compare";
import { DeltaPanel } from "./delta-panel";
import { FixPicker } from "./fix-picker";
import type { BallPathView, CameraView, ReplayLayout, SkeletonScene } from "./skeleton-scene";
import { buildTimeline, frameIndexAt, samplePose, type LoadedSwing, type Timeline } from "./swing";

/** One clip: the coach's verdict plus one compare file per ghost-ready fix. */
const CLIP = {
  coach: "/swings/coach_2116_bh_stereo.json",
  compare: [
    "/swings/compare_2116_hold_wrist_cock.json",
    "/swings/compare_2116_turn_shoulders_more.json",
    "/swings/compare_2116_straighten_elbow.json",
  ],
} as const;

const SLOW_MO = 0.25;
const THUMB_PX = 16; // native range thumb width, used to line the contact tick up with it

type Loaded = { compares: CompareResult[]; coach: CoachState };
type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: Loaded };
type Replay = { compare: CompareResult; timeline: Timeline };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function fetchJson<T>(url: string, parse: (value: unknown) => T, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Couldn't load ${url} (HTTP ${response.status}).`);
  let json: unknown;
  try {
    json = await response.json();
  } catch {
    throw new Error(`${url} isn't valid JSON. NaN or Infinity values aren't allowed.`);
  }
  try {
    return parse(json);
  } catch (error) {
    throw new Error(`${url} doesn't match the expected format: ${errorMessage(error)}.`);
  }
}

async function loadClip(signal: AbortSignal): Promise<Loaded> {
  // The coach caption is extra: if it fails, the replay still works and says why.
  const coach = fetchJson(CLIP.coach, parseCoach, signal).then(
    (caption): CoachState => ({ status: "ready", caption }),
    (error: unknown): CoachState => ({ status: "error", message: errorMessage(error) }),
  );
  const compares = await Promise.all(CLIP.compare.map((url) => fetchJson(url, parseCompare, signal)));
  const ids = new Set(compares.map((c) => c.fix.id));
  if (ids.size !== compares.length) throw new Error("Two compare files show the same fix.");
  return { compares, coach: await coach };
}

function formatTau(tau: number, step: number): string {
  if (Math.abs(tau) < step / 2) return "Contact";
  const ms = Math.round(Math.abs(tau) * 1000);
  return tau < 0 ? `${ms} ms before contact` : `${ms} ms after contact`;
}

function ballView(ball: BallPath, who: "you" | "ghost"): BallPathView {
  return { points: ball.points, bounces: ball.bounces, landing: ball.landing, label: `PREDICTED · ${who} · ${OUTCOME_WORDS[ball.outcome]}` };
}

function layoutFor({ compare }: Replay): ReplayLayout {
  return {
    floor: { you: compare.you.swing.floorY, ghost: compare.ghost.swing.floorY },
    contactSpot: compare.assumptions.contactSpot,
    ballPaths: { you: ballView(compare.you.ball, "you"), ghost: ballView(compare.ghost.ball, "ghost") },
  };
}

export function GhostReplay() {
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<LoadState>({ status: "loading" });
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [chosenFix, setChosenFix] = useState<string | null>(null);
  const [tau, setTau] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [slowMo, setSlowMo] = useState(false);
  const [sideBySide, setSideBySide] = useState(false);
  const [view, setView] = useState<CameraView>("player");

  // The animation loop reads these refs so it never restarts on a state change.
  const viewportRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<SkeletonScene | null>(null);
  const replayRef = useRef<Replay | null>(null);
  const tauRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const sideBySideRef = useRef(false);
  const viewRef = useRef<CameraView>("player");

  const loaded = load.status === "ready" ? load.data : null;
  const coach = loaded?.coach ?? null;
  const faults = useMemo(() => (coach?.status === "ready" ? coach.caption.faults : []), [coach]);
  // The ghost starts on the worst fault the coach found that physics can already fix.
  const compare = useMemo(() => {
    const all = loaded?.compares ?? [];
    const byFix = (id: string | undefined) => all.find((c) => c.fix.id === id);
    const coachPick = faults.map((f) => byFix(f.fix)).find((c) => c !== undefined);
    return byFix(chosenFix ?? undefined) ?? coachPick ?? all[0] ?? null;
  }, [loaded, chosenFix, faults]);
  const replay = useMemo<Replay | null>(
    () => (compare ? { compare, timeline: buildTimeline([compare.you.swing, compare.ghost.swing]) } : null),
    [compare],
  );

  useEffect(() => {
    replayRef.current = replay;
  }, [replay]);

  useEffect(() => {
    const controller = new AbortController();
    loadClip(controller.signal)
      .then((data) => {
        const first = data.compares[0];
        const timeline = buildTimeline([first.you.swing, first.ghost.swing]);
        // Respect reduced motion: start paused on the contact frame instead of autoplaying.
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        tauRef.current = reduceMotion ? 0 : timeline.start;
        playingRef.current = !reduceMotion;
        setTau(tauRef.current);
        setPlaying(!reduceMotion);
        setLoad({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoad({ status: "error", message: errorMessage(error) });
      });
    return () => controller.abort();
  }, [attempt]);

  // One scene for the page. New swings and ball paths are swapped in by the loop, so
  // changing the fix keeps the camera where the viewer left it.
  useEffect(() => {
    const container = viewportRef.current;
    if (!container) return;
    let cancelled = false;
    let frameId = 0;
    let scene: SkeletonScene | null = null;

    import("./skeleton-scene")
      .then(({ SkeletonScene }) => {
        if (cancelled) return;
        const s = new SkeletonScene(container);
        scene = s;
        sceneRef.current = s;
        s.setSideBySide(sideBySideRef.current);
        s.setView(viewRef.current);

        let applied: Replay | null = null;
        let last = performance.now();
        let drawnTau = Number.NaN;
        const tick = (now: number) => {
          const dt = Math.min((now - last) / 1000, 0.1);
          last = now;
          const r = replayRef.current;
          if (r !== applied) {
            applied = r;
            drawnTau = Number.NaN;
            if (r) s.setReplay(layoutFor(r));
          }
          if (r) {
            const { start, end } = r.timeline;
            const span = end - start;
            if (playingRef.current && span > 0) {
              let next = tauRef.current + dt * speedRef.current;
              if (next > end) next = start + ((next - end) % span);
              tauRef.current = next;
              setTau(next);
            }
            if (tauRef.current !== drawnTau) {
              drawnTau = tauRef.current;
              s.setPoses(samplePose(r.compare.you.swing, drawnTau), samplePose(r.compare.ghost.swing, drawnTau));
            }
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
  }, [attempt]);

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

  function toggleView() {
    const next: CameraView = view === "player" ? "court" : "player";
    viewRef.current = next;
    sceneRef.current?.setView(next);
    setView(next);
  }

  function retry() {
    setLoad({ status: "loading" });
    setSceneError(null);
    setAttempt((n) => n + 1);
  }

  const timeline = replay?.timeline;
  const span = timeline ? timeline.end - timeline.start : 0;
  const contactPct = timeline && span > 0 ? ((0 - timeline.start) / span) * 100 : 0;
  const youFrame = compare ? frameIndexAt(compare.you.swing, tau) : 0;
  const ghostFrame = compare ? frameIndexAt(compare.ghost.swing, tau) : 0;
  const timeLabel = timeline ? formatTau(tau, timeline.step) : "";
  const error = load.status === "error" ? load.message : sceneError;
  const ready = compare !== null;

  return (
    <section aria-label="Swing replay" className="flex flex-col gap-4">
      <div className="grid gap-2 text-sm sm:grid-cols-2">
        <SwingLegend colour={YOU_COLOUR} name="You" detail="as played" swing={compare?.you.swing} />
        <SwingLegend
          colour={GHOST_COLOUR}
          name="Ghost"
          detail={compare ? `${fixName(compare.fix.id).toLowerCase()} ${formatValue(compare.fix.amount, compare.fix.unit)}` : undefined}
          swing={compare?.ghost.swing}
          mockNote={compare && !compare.ghostIsReal ? "This ghost isn't a real fix: it's a copy of your swing." : undefined}
        />
      </div>

      {loaded && (
        <FixPicker compares={loaded.compares} selected={compare?.fix.id ?? null} faults={faults} onSelect={setChosenFix} />
      )}

      <div className="relative h-[min(68vh,680px)] min-h-96 overflow-hidden rounded-xl border bg-card">
        <div
          ref={viewportRef}
          role="img"
          aria-label="3D replay on a squash court: your swing and PREDICTED ball path in orange, the ghost and its PREDICTED ball path in cyan. Drag to rotate, scroll to zoom."
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
        {compare && !error && (
          <>
            <BallLegend compare={compare} />
            <p className="pointer-events-none absolute top-3 right-3 hidden max-w-[45%] text-right text-xs text-muted-foreground sm:block">
              Court 6.40 × 9.75 m · 1 m grid · player drawn beside the assumed contact spot (display only)
              <span className="block">Drag to rotate · Scroll to zoom · Right-drag to pan</span>
            </p>
            {coach && <CoachCaptionBar coach={coach} />}
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
            disabled={!ready}
            aria-valuetext={`${timeLabel}, your frame ${youFrame}, ghost frame ${ghostFrame}`}
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setPlayback(!playing)} disabled={!ready} className="min-w-24">
            {playing ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
            {playing ? "Pause" : "Play"}
          </Button>
          <Button variant={slowMo ? "secondary" : "outline"} onClick={toggleSlowMo} aria-pressed={slowMo} disabled={!ready}>
            <Turtle data-icon="inline-start" />
            0.25× slow-mo
          </Button>
          <Button variant="outline" onClick={() => seek(0)} disabled={!ready}>
            <Crosshair data-icon="inline-start" />
            Contact
          </Button>

          <p className="mx-auto px-2 font-mono text-xs text-muted-foreground tabular-nums">
            <span className="text-foreground">{timeLabel || "–"}</span>
            {ready && (
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

          <Button variant="outline" onClick={toggleView} disabled={!ready}>
            {view === "player" ? <Grid3x3 data-icon="inline-start" /> : <PersonStanding data-icon="inline-start" />}
            {view === "player" ? "Court view" : "Player view"}
          </Button>
          <Button variant="outline" onClick={toggleSideBySide} aria-pressed={sideBySide} disabled={!ready}>
            {sideBySide ? <Layers data-icon="inline-start" /> : <Columns2 data-icon="inline-start" />}
            {sideBySide ? "Overlay" : "Side by side"}
          </Button>
          <Button variant="ghost" onClick={() => sceneRef.current?.resetView()} disabled={!ready}>
            <RotateCcw data-icon="inline-start" />
            Reset view
          </Button>
        </div>
      </div>

      {compare && (
        <DeltaPanel
          compare={compare}
          flagged={faults.some((f) => f.fix === compare.fix.id)}
          coachLoaded={coach?.status === "ready"}
        />
      )}
    </section>
  );
}

function BallLegend({ compare }: { compare: CompareResult }) {
  const rows = [
    { who: "You", colour: YOU_COLOUR, ball: compare.you.ball },
    { who: "Ghost", colour: GHOST_COLOUR, ball: compare.ghost.ball },
  ];
  return (
    <div className="pointer-events-none absolute top-3 left-3 flex flex-col gap-1 rounded-lg border bg-background/90 px-2.5 py-2 text-xs">
      <p className="font-mono font-semibold tracking-wide">PREDICTED ball paths</p>
      {rows.map(({ who, colour, ball }) => (
        <p key={who} className="flex items-center gap-2 tabular-nums">
          <span aria-hidden className="h-0.5 w-5 rounded-full" style={{ backgroundColor: colour }} />
          <span style={{ color: colour }}>{who}</span>
          <span className="text-muted-foreground">
            {OUTCOME_WORDS[ball.outcome]} · {ball.speedKmh} km/h
          </span>
        </p>
      ))}
    </div>
  );
}

function SwingLegend({
  colour,
  name,
  detail,
  swing,
  mockNote,
}: {
  colour: string;
  name: string;
  detail?: string;
  swing: LoadedSwing | undefined;
  mockNote?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border bg-card px-3 py-2.5">
      <span aria-hidden className="mt-1.5 size-2.5 shrink-0 rounded-full" style={{ backgroundColor: colour }} />
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="flex flex-wrap items-center gap-x-2 font-medium">
          {name}
          {detail && <span className="font-normal text-muted-foreground">{detail}</span>}
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
