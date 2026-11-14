"use client";

// The /ghost demo flow: 1 pick a swing, 2 the coach's call, 3 the ghost makes the fix,
// 4 both PREDICTED ball paths on the court. Owns which swing, step and fix are shown;
// data comes from sources.ts (live service or saved samples), the 3D view from ghost-stage.tsx.
// /ghost?swing=<id> opens on that swing at the coach's call (how /upload shows a new swing).

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, RotateCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CoachCaptionBar, type CaptionState } from "./coach-caption";
import { CoachDetails } from "./coach-details";
import {
  fixName,
  formatValue,
  OUTCOME_WORDS,
  sameBallPath,
  swingCoordinates,
  type BallPath,
  type Catalogue,
} from "./compare";
import { BallChanges, BodyChanges } from "./delta-panel";
import { FixPicker } from "./fix-picker";
import { GhostStage, type StageStatus } from "./ghost-stage";
import { SceneLegend } from "./scene-legend";
import type { BallPathView, CameraView } from "./skeleton-scene";
import {
  buildEntries,
  checkApi,
  coachPickFix,
  fixOptionsFor,
  resolveSelection,
  loadCatalogue,
  loadCoachFor,
  loadCompareFor,
  loadSwingFor,
  type ApiState,
  type FixOption,
} from "./sources";
import type { SwingCoordinates } from "./swing";
import { SwingPicker, type CatalogueState } from "./swing-picker";
import { useAsync, type Async } from "./use-async";

const STEPS = [
  {
    id: "swing",
    title: "Pick a swing",
    heading: "Pick a swing",
    intro: "One swing, filmed in slow motion and turned into a 3D skeleton.",
    next: null,
  },
  {
    id: "coach",
    title: "Coach's call",
    heading: "The coach's call",
    intro: "Code measured the swing. The coach names the one fix that matters most.",
    next: "Show the ghost",
  },
  {
    id: "ghost",
    title: "The ghost",
    heading: "Your ghost makes the fix",
    intro: "Orange is the swing you played. Cyan is the same swing with one fix applied by physics.",
    next: "Show the court",
  },
  {
    id: "court",
    title: "On court",
    heading: "Where the ball goes",
    intro: "Ball paths are PREDICTED from the estimated racket speed. There is no real ball.",
    next: "Try another swing",
  },
] as const;
type Step = (typeof STEPS)[number]["id"];

function ballView(ball: BallPath, who: string): BallPathView {
  return {
    points: ball.points,
    bounces: ball.bounces,
    landing: ball.landing,
    label: `PREDICTED · ${who} · ${OUTCOME_WORDS[ball.outcome]}`,
  };
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Reads ?swing=<id>. page.tsx wraps this in Suspense, as useSearchParams needs when prerendering. */
export function GhostDemoFromUrl() {
  const requested = useSearchParams().get("swing")?.trim() || null;
  // Keyed, so a new ?swing= starts the flow fresh (and re-reads the live list) even when Next
  // kept this page alive in the background.
  return <GhostDemo key={requested ?? ""} requestedSwing={requested} />;
}

export function GhostDemo({ requestedSwing }: { requestedSwing: string | null }) {
  const [step, setStep] = useState<Step>(requestedSwing ? "coach" : "swing");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [chosenFix, setChosenFix] = useState<string | null>(null);
  const [view, setView] = useState<CameraView>("player");
  // One retry counter per request, so Try again refetches only what failed.
  const [swingAttempt, setSwingAttempt] = useState(0);
  const [coachAttempt, setCoachAttempt] = useState(0);
  const [compareAttempt, setCompareAttempt] = useState(0);
  const [catalogueAttempt, setCatalogueAttempt] = useState(0);
  const [catalogue, setCatalogue] = useState<Async<Catalogue>>({ status: "loading" });
  const [apiAttempt, setApiAttempt] = useState(0);
  const [api, setApi] = useState<ApiState>({ status: "checking" });

  const headingRef = useRef<HTMLHeadingElement>(null);
  const focusHeading = useRef(false);

  // App-wide data loads after mount, so nothing is fetched while the page is prerendered.
  useEffect(() => {
    let live = true;
    loadCatalogue(catalogueAttempt).then(
      (value) => live && setCatalogue({ status: "ready", value }),
      (error: unknown) => live && setCatalogue({ status: "error", message: errorText(error) }),
    );
    return () => {
      live = false;
    };
  }, [catalogueAttempt]);

  useEffect(() => {
    let live = true;
    checkApi().then((state) => live && setApi(state));
    return () => {
      live = false;
    };
  }, [apiAttempt]);

  useEffect(() => {
    if (!focusHeading.current) return;
    focusHeading.current = false;
    headingRef.current?.focus();
  }, [step]);

  const entries = useMemo(
    () => (catalogue.status === "ready" ? buildEntries(catalogue.value, api) : []),
    [catalogue, api],
  );
  const demoEntry = useMemo(() => entries.find((e) => e.isDefault) ?? null, [entries]);
  // The linked swing (?swing=) or the demo swing only while nothing is picked; never a silent
  // switch away from a picked swing.
  const selection = useMemo(
    () =>
      resolveSelection(
        entries,
        selectedKey,
        { samples: catalogue.status === "ready", live: api.status !== "checking" },
        requestedSwing,
      ),
    [entries, selectedKey, catalogue.status, api.status, requestedSwing],
  );
  const entry = selection.entry;
  // The linked swing isn't in either list: say which one and offer a re-check of the live list.
  const missing =
    selection.gone && selectedKey === null && requestedSwing !== null
      ? { id: requestedSwing, offline: api.status === "offline", onRetry: retryApi }
      : null;

  // Per swing: the swing itself, the coach's verdict and the ghost for the active fix.
  const swingPromise = useMemo(() => (entry ? loadSwingFor(entry, swingAttempt) : null), [entry, swingAttempt]);
  const coachPromise = useMemo(() => (entry ? loadCoachFor(entry, coachAttempt) : null), [entry, coachAttempt]);
  const swing = useAsync(swingPromise);
  const coach = useAsync(coachPromise);
  const coachCaption = coach.status === "ready" ? coach.value : null;
  const coachSettled = coach.status === "ready" || coach.status === "error";
  const faults = useMemo(() => coachCaption?.faults ?? [], [coachCaption]);
  const fixes = useMemo(() => (entry ? fixOptionsFor(entry, coachCaption) : []), [entry, coachCaption]);

  const coachPick = useMemo(() => coachPickFix(fixes, coachCaption), [fixes, coachCaption]);

  const activeFix = useMemo<FixOption | null>(() => {
    const usable = fixes.filter((f) => f.unavailable === null);
    const chosen = usable.find((f) => f.id === chosenFix);
    if (chosen) return chosen;
    if (!coachSettled) return null; // wait for the coach so the ghost doesn't switch under you
    return coachPick ?? usable[0] ?? null;
  }, [fixes, chosenFix, coachSettled, coachPick]);

  const comparePromise = useMemo(
    () => (entry && activeFix ? loadCompareFor(entry, activeFix, compareAttempt) : null),
    [entry, activeFix, compareAttempt],
  );
  const compareState = useAsync(comparePromise);
  const compare = compareState.status === "ready" ? compareState.value : null;

  const showGhost = step === "ghost" || step === "court";
  const onCourt = step === "court";
  const samePath = compare ? sameBallPath(compare.you.ball, compare.ghost.ball) : false;
  const you = compare?.you.swing ?? (swing.status === "ready" ? swing.value : null);
  // Follows where `you` comes from: compare's swings use its coordinateSystem ("court" = draw as
  // given); the raw swing shown before a compare loads is always a hip-centred pipeline skeleton.
  const coordinates = useMemo<SwingCoordinates>(
    () => (compare ? swingCoordinates(compare, onCourt) : { system: "hip-centred", youWrist: null }),
    [compare, onCourt],
  );
  const balls = useMemo(() => {
    if (!onCourt || !compare) return null;
    // Identical paths: draw one, and the legend says the fix changes the body, not the ball.
    return samePath
      ? { you: ballView(compare.you.ball, "you and ghost"), ghost: null }
      : { you: ballView(compare.you.ball, "you"), ghost: ballView(compare.ghost.ball, "ghost") };
  }, [onCourt, compare, samePath]);

  const caption: CaptionState =
    coach.status === "ready"
      ? { kind: "ready", caption: coach.value }
      : coach.status === "error"
        ? { kind: "error", message: coach.message, onRetry: () => setCoachAttempt((n) => n + 1) }
        : { kind: "loading" };

  const stageStatus: StageStatus = you
    ? null
    : swing.status === "error"
      ? { kind: "error", message: swing.message, onRetry: () => setSwingAttempt((n) => n + 1) }
      : { kind: "loading", message: "Loading swing…" };

  const catalogueState: CatalogueState =
    catalogue.status === "error"
      ? { status: "error", message: catalogue.message, onRetry: retryCatalogue }
      : catalogue.status === "ready"
        ? { status: "ready" }
        : { status: "loading" };

  function goTo(next: Step) {
    focusHeading.current = true;
    setStep(next);
    setView(next === "court" ? "court" : "player");
  }

  function pickSwing(key: string) {
    if (key !== entry?.key) setChosenFix(null);
    setSelectedKey(key);
    goTo("coach");
  }

  /** After a picked swing is gone: the user chooses the demo swing (or the list), never automatically. */
  function leaveGoneSwing() {
    if (demoEntry) {
      pickSwing(demoEntry.key);
    } else {
      setSelectedKey(null);
      goTo("swing");
    }
  }

  function retryCatalogue() {
    setCatalogue({ status: "loading" });
    setCatalogueAttempt((n) => n + 1);
  }

  function retryApi() {
    setApi({ status: "checking" });
    setApiAttempt((n) => n + 1);
  }

  const index = STEPS.findIndex((s) => s.id === step);
  const meta = STEPS[index];

  return (
    <div className="flex flex-col gap-5">
      <StepNav step={step} canAdvance={entry !== null} onGo={goTo} />

      <div className="flex flex-col gap-1">
        <h2 ref={headingRef} tabIndex={-1} className="text-2xl font-semibold tracking-tight outline-none sm:text-3xl">
          {meta.heading}
        </h2>
        <p className="text-sm text-muted-foreground sm:text-base">{meta.intro}</p>
      </div>

      {step === "swing" ? (
        <>
          {selection.gone && <SwingGone hasDemo={demoEntry !== null} onLeave={leaveGoneSwing} missing={missing} />}
          <SwingPicker
            catalogue={catalogueState}
            entries={entries}
            api={api}
            selectedKey={entry?.key ?? null}
            onPick={pickSwing}
            onRetryApi={retryApi}
          />
        </>
      ) : !entry ? (
        selection.gone ? (
          <SwingGone hasDemo={demoEntry !== null} onLeave={leaveGoneSwing} missing={missing} />
        ) : catalogue.status === "error" ? (
          // Reachable when a ?swing= link opens on this step: without the catalogue there are no swings.
          <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border bg-card p-6">
            <p className="text-sm">The swings couldn&apos;t load: {catalogue.message}</p>
            <Button variant="outline" onClick={retryCatalogue}>
              <RotateCcw data-icon="inline-start" />
              Try again
            </Button>
          </div>
        ) : (
          <p role="status" className="rounded-xl border bg-card p-6 text-sm text-muted-foreground">
            Loading swings…
          </p>
        )
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={() => goTo(STEPS[index - 1].id)}>
              <ArrowLeft data-icon="inline-start" />
              Back
            </Button>
            <p className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
              <Badge variant={entry.origin === "api" ? "default" : "secondary"}>
                {entry.origin === "api" ? "Live" : "Sample"}
              </Badge>
              <span className="truncate">{entry.label}</span>
            </p>
            {meta.next && (
              <Button size="lg" className="ml-auto" onClick={() => goTo(step === "court" ? "swing" : STEPS[index + 1].id)}>
                {meta.next}
                <ArrowRight data-icon="inline-end" />
              </Button>
            )}
          </div>

          {showGhost && (
            <div className="flex flex-col gap-2">
              <FixPicker
                fixes={fixes}
                selected={activeFix?.id ?? null}
                loading={compareState.status === "loading"}
                faults={faults}
                coachPick={coachPick?.id ?? null}
                coached={coachCaption !== null}
                onSelect={setChosenFix}
              />
              <p role="status" className="text-sm text-muted-foreground empty:hidden">
                {compareState.status === "loading" && activeFix ? `Making the ${fixName(activeFix.id).toLowerCase()} ghost…` : ""}
              </p>
              {compareState.status === "error" && (
                <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/40 bg-card p-3 text-sm">
                  <p className="flex-1">Couldn&apos;t make this ghost: {compareState.message}</p>
                  <Button variant="outline" size="sm" onClick={() => setCompareAttempt((n) => n + 1)}>
                    Try again
                  </Button>
                </div>
              )}
            </div>
          )}

          <GhostStage
            you={you}
            ghost={showGhost && compare ? compare.ghost.swing : null}
            balls={balls}
            coordinates={coordinates}
            view={view}
            onViewChange={setView}
            status={stageStatus}
          >
            <SceneLegend
              ghost={
                showGhost && compare
                  ? {
                      label: `${fixName(compare.fix.id).toLowerCase()} ${formatValue(compare.fix.amount, compare.fix.unit)}`,
                      mock: !compare.ghostIsReal,
                    }
                  : null
              }
              balls={onCourt && compare ? { you: compare.you.ball, ghost: compare.ghost.ball, same: samePath } : null}
              monoDepth={you?.source === "mono"}
            />
            {onCourt && (
              <p className="pointer-events-none absolute top-3 right-3 hidden max-w-[34%] text-right text-xs text-muted-foreground md:block">
                {coordinates.system === "court"
                  ? "Court 6.40 × 9.75 m · player where physics placed them"
                  : "Court 6.40 × 9.75 m · player placed with the hitting hand over the ball's assumed start (display only)"}
              </p>
            )}
            <CoachCaptionBar state={caption} size={step === "coach" ? "large" : "compact"} />
          </GhostStage>

          {step === "coach" && <CoachDetails state={caption} />}
          {showGhost && compare && (
            <div className={cn("grid gap-3", onCourt && "lg:grid-cols-2")}>
              {onCourt && <BallChanges compare={compare} samePath={samePath} />}
              <BodyChanges
                compare={compare}
                flagged={faults.some((f) => f.fix === compare.fix.id)}
                coached={coachCaption !== null}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * A picked swing dropped out of the list, or the ?swing= one (`missing`) isn't in it. Says so
 * instead of switching swings behind the user's back.
 */
function SwingGone({
  hasDemo,
  onLeave,
  missing,
}: {
  hasDemo: boolean;
  onLeave: () => void;
  missing: { id: string; offline: boolean; onRetry: () => void } | null;
}) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-xl border bg-card p-6">
      {missing ? (
        <p className="text-sm">
          Swing <span className="font-mono break-all">{missing.id}</span> isn&apos;t in the list.{" "}
          {missing.offline
            ? "The live Python service isn't answering, so only the saved samples are listed."
            : "The live Python service doesn't list it, so the link may be out of date."}
        </p>
      ) : (
        <p className="text-sm">That swing isn&apos;t available any more.</p>
      )}
      <div className="flex flex-wrap gap-2">
        {missing && (
          <Button variant="outline" onClick={missing.onRetry}>
            <RotateCcw data-icon="inline-start" />
            Check again
          </Button>
        )}
        <Button variant="outline" onClick={onLeave}>
          <ArrowLeft data-icon="inline-start" />
          {hasDemo ? "Back to the demo swing" : "Pick a swing"}
        </Button>
      </div>
    </div>
  );
}

function StepNav({ step, canAdvance, onGo }: { step: Step; canAdvance: boolean; onGo: (step: Step) => void }) {
  const current = STEPS.findIndex((s) => s.id === step);
  return (
    <nav aria-label="Demo steps">
      <ol className="flex flex-wrap gap-2">
        {STEPS.map((s, i) => {
          const isCurrent = i === current;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onGo(s.id)}
                disabled={i > 0 && !canAdvance && !isCurrent}
                aria-current={isCurrent ? "step" : undefined}
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors outline-none",
                  "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-40",
                  isCurrent
                    ? "border-foreground bg-foreground text-background"
                    : i < current
                      ? "text-foreground hover:bg-muted"
                      : "text-muted-foreground hover:bg-muted",
                )}
              >
                <span className="font-mono text-xs tabular-nums">{i + 1}</span>
                {s.title}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
