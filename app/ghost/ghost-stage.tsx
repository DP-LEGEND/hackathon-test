"use client";

// The 3D stage: your swing (orange), optionally the ghost (cyan) aligned at contact, and
// optionally both PREDICTED ball paths. Owns the playback clock and camera buttons; what to
// show comes from the demo flow (ghost-demo.tsx). The three.js scene is loaded on demand.

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type CSSProperties, type ReactNode } from "react";
import {
  CircleAlert,
  Columns2,
  Crosshair,
  Grid3x3,
  Layers,
  LoaderCircle,
  Pause,
  PersonStanding,
  Play,
  RotateCcw,
  Turtle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import { JointLegend } from "./joint-legend";
import { look } from "./look";
import { fadedJointsAt, jointWords, summariseGuesses } from "./provenance";
import type { BallPathView, CameraView, ReplayLayout, SkeletonScene } from "./skeleton-scene";
import {
  buildTimeline,
  frameIndexAt,
  samplePose,
  type LoadedSwing,
  type SwingCoordinates,
  type Timeline,
} from "./swing";

const SLOW_MO = 0.25;
const THUMB_PX = 16; // native range thumb width, used to line the contact tick up with it

export type StageStatus =
  | { kind: "loading"; message: string }
  | { kind: "error"; message: string; onRetry: () => void }
  | null;

type StageLayout = { you: LoadedSwing; ghost: LoadedSwing | null; timeline: Timeline; scene: ReplayLayout };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatTau(tau: number, step: number): string {
  if (Math.abs(tau) < step / 2) return "Contact";
  const ms = Math.round(Math.abs(tau) * 1000);
  return tau < 0 ? `${ms} ms before contact` : `${ms} ms after contact`;
}

export function GhostStage({
  you,
  ghost,
  balls,
  coordinates,
  view,
  onViewChange,
  status,
  legend,
  children,
}: {
  you: LoadedSwing | null;
  /** Null hides the ghost. */
  ghost: LoadedSwing | null;
  /** Null hides the ball paths; ghost null draws one shared path. */
  balls: { you: BallPathView; ghost: BallPathView | null } | null;
  /** How the swings sit on the court: hip-centred (turned and placed) or court (drawn as given). */
  coordinates: SwingCoordinates;
  view: CameraView;
  onViewChange: (view: CameraView) => void;
  /** Covers the view while the swing loads or fails. */
  status: StageStatus;
  /** The key to the view, top left under the view's name. */
  legend?: ReactNode;
  /** Other overlays drawn over the view (caption, court note). */
  children?: ReactNode;
}) {
  const [sceneError, setSceneError] = useState<string | null>(null);
  const [sceneAttempt, setSceneAttempt] = useState(0);
  const [tau, setTau] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [slowMo, setSlowMo] = useState(false);
  const [sideBySide, setSideBySide] = useState(false);

  // The animation loop reads these refs so it never restarts on a state change.
  const viewportRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<SkeletonScene | null>(null);
  const layoutRef = useRef<StageLayout | null>(null);
  const tauRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const sideBySideRef = useRef(false);
  const viewRef = useRef<CameraView>(view);

  const layout = useMemo<StageLayout | null>(() => {
    if (!you) return null;
    return {
      you,
      ghost,
      timeline: buildTimeline(ghost ? [you, ghost] : [you]),
      scene: { floor: { you: you.floorY, ghost: ghost?.floorY ?? you.floorY }, coordinates, ballPaths: balls },
    };
  }, [you, ghost, balls, coordinates]);

  useEffect(() => {
    layoutRef.current = layout;
  }, [layout]);

  useEffect(() => {
    viewRef.current = view;
    sceneRef.current?.setView(view);
  }, [view]);

  // One scene for the stage. New swings and ball paths are swapped in by the loop, so
  // changing the fix or the step keeps the camera where the viewer left it.
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
        // The PREDICTED tags keep clear of whatever is laid over the view (marked data-tag-avoid).
        s.setTagOverlays(() =>
          Array.from(container.parentElement?.querySelectorAll<HTMLElement>("[data-tag-avoid]") ?? [], (el) =>
            el.getBoundingClientRect(),
          ),
        );

        let applied: StageLayout | null = null;
        let started = false;
        let last = performance.now();
        let drawnTau = Number.NaN;
        const tick = (now: number) => {
          const dt = Math.min((now - last) / 1000, 0.1);
          last = now;
          const l = layoutRef.current;
          if (l !== applied) {
            applied = l;
            drawnTau = Number.NaN;
            if (l) {
              s.setReplay(l.scene);
              const { start, end } = l.timeline;
              if (!started) {
                // Respect reduced motion: start paused on the contact frame instead of autoplaying.
                started = true;
                const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
                tauRef.current = reduceMotion ? 0 : start;
                playingRef.current = !reduceMotion;
                setPlaying(!reduceMotion);
              }
              tauRef.current = Math.min(Math.max(tauRef.current, start), end);
              setTau(tauRef.current);
            }
          }
          if (l) {
            const { start, end } = l.timeline;
            const span = end - start;
            if (playingRef.current && span > 0) {
              let next = tauRef.current + dt * speedRef.current;
              if (next > end) next = start + ((next - end) % span);
              tauRef.current = next;
              setTau(next);
            }
            if (tauRef.current !== drawnTau) {
              drawnTau = tauRef.current;
              s.setPoses(samplePose(l.you, drawnTau), l.ghost ? samplePose(l.ghost, drawnTau) : null);
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
  }, [sceneAttempt]);

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

  function retryScene() {
    setSceneError(null);
    setSceneAttempt((n) => n + 1);
  }

  const timeline = layout?.timeline;
  const span = timeline ? timeline.end - timeline.start : 0;
  const contactPct = timeline && span > 0 ? ((0 - timeline.start) / span) * 100 : 0;
  const youFrame = you ? frameIndexAt(you, tau) : 0;
  const ghostFrame = ghost ? frameIndexAt(ghost, tau) : 0;
  const timeLabel = timeline ? formatTau(tau, timeline.step) : "";
  const guessSummary = useMemo(() => (you ? summariseGuesses(you.guessed) : null), [you]);
  // Joints drawn faded on your current frame, named so the fade is never only visual.
  const fadedNow = you ? [...new Set(fadedJointsAt(you.guessed, youFrame).map(jointWords))] : [];
  const fadedLabel = fadedNow.length > 2 ? `${fadedNow.slice(0, 2).join(", ")} +${fadedNow.length - 2}` : fadedNow.join(", ");
  // Solid joints count as measured only on a frame the file marks, for every figure drawn, and
  // only when the file records visibility (summary.fields): with just `filled` or
  // `approximatedJoints`, the legend says "not flagged as guessed" instead of "measured from video".
  const marked =
    you !== null && you.guessed.recorded[youFrame] === true && (ghost === null || ghost.guessed.recorded[ghostFrame] === true);
  const ready = layout !== null;
  const error = sceneError
    ? { message: sceneError, onRetry: retryScene }
    : status?.kind === "error"
      ? { message: status.message, onRetry: status.onRetry }
      : null;

  // The scrubber's mint fill ends under the thumb's centre (the thumb travels inside the track).
  const played = timeline && span > 0 ? Math.min(Math.max((tau - timeline.start) / span, 0), 1) : 0;
  const scrubStyle = { "--fill": `calc(${played} * (100% - ${THUMB_PX}px) + ${THUMB_PX / 2}px)` } as CSSProperties;
  const toggle = "aria-pressed:border-primary aria-pressed:bg-accent aria-pressed:text-primary";

  return (
    <section aria-label="Swing replay" className="flex flex-col gap-3">
      <div className="overflow-hidden rounded-[24px] border bg-(--media)">
        <div className="relative h-[min(62vh,680px)] min-h-[24rem]">
          <div
            ref={viewportRef}
            role="img"
            aria-label="3D replay on a squash court: your swing in orange, the ghost and its fix in cyan, PREDICTED ball paths when shown. Drag to rotate, scroll to zoom."
            className="absolute inset-0 cursor-grab active:cursor-grabbing"
          />
          {status?.kind === "loading" && !error && (
            <div
              role="status"
              className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-sm text-muted-foreground"
            >
              <LoaderCircle aria-hidden className="size-6 text-primary motion-safe:animate-spin" />
              {status.message}
            </div>
          )}
          {error && (
            <div
              role="alert"
              className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-(--media) p-6 text-center"
            >
              <CircleAlert aria-hidden className="size-6 text-destructive" />
              <p className="max-w-md text-sm text-foreground">{error.message}</p>
              <Button variant="outline" className={look.pill} onClick={error.onRetry}>
                <RotateCcw data-icon="inline-start" />
                Try again
              </Button>
            </div>
          )}
          {ready && !error && (
            <div
              data-tag-avoid
              className="pointer-events-none absolute top-3 left-3 flex max-w-[calc(100%-1.5rem)] flex-col items-start gap-2.5 sm:top-5 sm:left-5 sm:max-w-xs"
            >
              <p className={cn(look.label, "flex flex-wrap gap-x-2.5 [text-shadow:0_1px_2px_rgb(0_0_0/0.6)]")}>
                <span className="text-primary">{view === "player" ? "Player view" : "Court view"}</span>
                <span className="text-muted-foreground">3D replay</span>
              </p>
              {legend}
            </div>
          )}
          {ready && !error && children}
        </div>

        <div className="flex flex-col gap-3 border-t bg-(--panel) px-3 py-3 sm:px-5 sm:py-4">
          <div className="flex items-center gap-3 sm:gap-4">
            <Button
              size="icon"
              aria-label={playing ? "Pause" : "Play"}
              onClick={() => setPlayback(!playing)}
              disabled={!ready}
              className="size-11 shrink-0 rounded-full"
            >
              {playing ? <Pause className="size-5" /> : <Play className="size-5 translate-x-px" />}
            </Button>
            <div className="relative min-w-0 flex-1 pt-4">
              {timeline && (
                <span
                  aria-hidden
                  className="pointer-events-none absolute top-0 flex h-[30px] -translate-x-1/2 flex-col items-center text-[0.65rem] leading-none text-muted-foreground"
                  style={{ left: `calc(${contactPct}% + ${(0.5 - contactPct / 100) * THUMB_PX}px)` }}
                >
                  contact
                  <span className="mt-0.5 w-px flex-1 bg-muted-foreground/70" />
                </span>
              )}
              <label htmlFor="ghost-scrub" className="sr-only">
                Swing time
              </label>
              <input
                id="ghost-scrub"
                type="range"
                className="ghost-swing-range"
                style={scrubStyle}
                min={timeline?.start ?? 0}
                max={timeline?.end ?? 1}
                step={timeline?.step ?? 0.01}
                value={tau}
                onChange={onScrub}
                disabled={!ready}
                aria-valuetext={`${timeLabel}, your frame ${youFrame}${ghost ? `, ghost frame ${ghostFrame}` : ""}${
                  fadedNow.length > 0 ? `, estimated: ${fadedNow.join(", ")}` : ""
                }`}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <p className="w-full font-mono text-xs text-muted-foreground tabular-nums sm:mr-auto sm:w-auto">
              <span className="text-foreground">{timeLabel || "–"}</span>
              {ready && (
                <>
                  {" · "}
                  <span style={{ color: YOU_COLOUR }}>you f{youFrame}</span>
                  {fadedLabel && <span className="opacity-60"> (est. {fadedLabel})</span>}
                  {ghost && (
                    <>
                      {" · "}
                      <span style={{ color: GHOST_COLOUR }}>ghost f{ghostFrame}</span>
                    </>
                  )}
                  {" · "}
                  {slowMo ? `${SLOW_MO}×` : "1×"}
                </>
              )}
            </p>
            <Button
              variant="outline"
              className={cn(look.pill, toggle)}
              onClick={toggleSlowMo}
              aria-pressed={slowMo}
              disabled={!ready}
            >
              <Turtle data-icon="inline-start" />
              0.25× slow-mo
            </Button>
            <Button variant="outline" className={look.pill} onClick={() => seek(0)} disabled={!ready}>
              <Crosshair data-icon="inline-start" />
              Contact
            </Button>
            <Button
              variant="outline"
              className={look.pill}
              onClick={() => onViewChange(view === "player" ? "court" : "player")}
              disabled={!ready}
            >
              {view === "player" ? <Grid3x3 data-icon="inline-start" /> : <PersonStanding data-icon="inline-start" />}
              {view === "player" ? "Court view" : "Player view"}
            </Button>
            <Button
              variant="outline"
              className={cn(look.pill, toggle)}
              onClick={toggleSideBySide}
              aria-pressed={sideBySide}
              disabled={!ready || !ghost}
            >
              {sideBySide ? <Layers data-icon="inline-start" /> : <Columns2 data-icon="inline-start" />}
              {sideBySide ? "Overlay" : "Side by side"}
            </Button>
            <Button variant="ghost" className={look.pill} onClick={() => sceneRef.current?.resetView()} disabled={!ready}>
              <RotateCcw data-icon="inline-start" />
              Reset view
            </Button>
          </div>
          {sideBySide && ghost && coordinates.system === "court" && balls?.ghost && (
            <p className="text-xs text-muted-foreground">
              Side by side: the ghost and its PREDICTED ball path are drawn to the side, so the ghost&apos;s ball lands
              off its real spot (display only).
            </p>
          )}
        </div>
      </div>

      {ready && !error && <JointLegend summary={guessSummary} marked={marked} />}
    </section>
  );
}
