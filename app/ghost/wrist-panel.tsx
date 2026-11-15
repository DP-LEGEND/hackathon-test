// Wrist sensor panel (step 2): what the phone strapped to the forearm measured around contact,
// and the coach's rolled_wrist call. Shown only when the swing has sensor data (wrist.ts).
// Every number is read from the files; the browser measures nothing. Orange = what the
// player did. Charts follow the dataviz rules: one series per chart (two small multiples, never
// two y-scales), 2px lines, hairline grid, a crosshair readout on hover and arrow keys, and a
// table with the same numbers.

import { useId, useRef, useState, type KeyboardEvent, type PointerEvent, type Ref } from "react";
import { Check, CircleHelp, RotateCcw, RotateCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { CaptionState } from "./coach-caption";
import { YOU_COLOUR } from "./colours";
import type { CoachFault } from "./compare";
import { look } from "./look";
import type { Async } from "./use-async";
import { sampleAt, type WristSeries } from "./wrist";

const deg = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

function formatDeg(value: number | null): string {
  return value === null ? "—" : `${deg.format(value + 0)}°`;
}

function formatRate(value: number | null): string {
  return value === null ? "—" : `${whole.format(value)}°/s`;
}

/** "−150 ms", "contact", "+100 ms" */
function formatMs(t: number): string {
  if (t === 0) return "contact";
  return `${t < 0 ? "−" : "+"}${Math.abs(t)} ms`;
}

export function WristSensorPanel({
  state,
  expected,
  caption,
  onRetry,
}: {
  state: Async<WristSeries | null>;
  /** The swing names a wrist file, so a load in progress is worth showing. */
  expected: boolean;
  caption: CaptionState;
  onRetry: () => void;
}) {
  if (state.status === "error") {
    return (
      <section aria-label="Wrist sensor" className={cn(look.card, look.pad)}>
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-muted-foreground">The wrist sensor data didn&apos;t load: {state.message}</p>
          <Button variant="outline" size="sm" className={look.pill} onClick={onRetry}>
            <RotateCcw data-icon="inline-start" />
            Try again
          </Button>
        </div>
      </section>
    );
  }
  if (state.status === "loading" && expected) {
    return (
      <p role="status" className={cn(look.card, look.pad, "text-sm text-muted-foreground")}>
        Loading wrist sensor data…
      </p>
    );
  }
  // No sensor data for this swing: no panel.
  if (state.status !== "ready" || state.value === null) return null;
  return <Panel series={state.value} caption={caption} />;
}

type Verdict =
  | { kind: "waiting" }
  | { kind: "rolled"; fault: CoachFault | null }
  | { kind: "firm"; rollDeg: number | null }
  | { kind: "not-judged"; why: string | null };

/** The coach's rolled_wrist call. The fault library decides; nothing here judges the numbers. */
function verdictFrom(caption: CaptionState): Verdict | null {
  if (caption.kind === "loading") return { kind: "waiting" };
  if (caption.kind === "error") return null;
  const c = caption.caption;
  if (c.firedFaultIds.includes("rolled_wrist")) {
    const fault = c.faults.find((f) => f.id === "rolled_wrist") ?? (c.fault?.id === "rolled_wrist" ? c.fault : null);
    return { kind: "rolled", fault };
  }
  if (c.wristSensor.source !== null) return { kind: "firm", rollDeg: c.wristSensor.rollDeg };
  return { kind: "not-judged", why: c.wristSensor.skipped };
}

function VerdictBadge({ verdict }: { verdict: Verdict | null }) {
  if (verdict === null || verdict.kind === "waiting") return null;
  if (verdict.kind === "rolled") {
    return (
      <Badge variant="outline" className="h-6 px-2.5 text-sm" style={{ borderColor: YOU_COLOUR }}>
        <RotateCw data-icon="inline-start" style={{ color: YOU_COLOUR }} />
        Rolled wrist
      </Badge>
    );
  }
  if (verdict.kind === "firm") {
    return (
      <Badge variant="outline" className="h-6 px-2.5 text-sm">
        <Check data-icon="inline-start" />
        Firm wrist
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="h-6 px-2.5 text-sm text-muted-foreground">
      <CircleHelp data-icon="inline-start" />
      Not judged
    </Badge>
  );
}

function verdictText(verdict: Verdict | null): string | null {
  if (verdict === null) return null;
  switch (verdict.kind) {
    case "waiting":
      return "Waiting for the coach's call on the wrist…";
    case "rolled": {
      const f = verdict.fault;
      if (!f || f.value === null || f.threshold === null) return "The coach's rolled_wrist fault fired for this swing.";
      const line = `${formatDeg(f.threshold)}${f.source ? ` (set from ${f.source})` : ""}`;
      return `The coach's rolled_wrist fault fired: the forearm rolled ${formatDeg(f.value)} through contact, past its ${line} line.`;
    }
    case "firm":
      return `The coach's rolled_wrist fault didn't fire${verdict.rollDeg !== null ? `: the forearm rolled ${formatDeg(verdict.rollDeg)} through contact` : ""}.`;
    case "not-judged":
      return `The coach didn't read the sensor for this swing${verdict.why ? ` (${verdict.why})` : ""}, so there's no rolled-wrist call.`;
  }
}

function Panel({ series, caption }: { series: WristSeries; caption: CaptionState }) {
  const verdict = verdictFrom(caption);
  const explanation = verdictText(verdict);
  const speedAtContact = sampleAt(series.turnRate, 0);
  const coachSensor = caption.kind === "ready" ? caption.caption.wristSensor : null;
  const rollRate = coachSensor?.rollRateDps ?? null;
  const tagFor = (mock: boolean) => (mock ? "MEASURED (sensor) · MOCK" : "MEASURED (sensor)");
  const tag = tagFor(series.mock);
  const [w0, w1] = series.windowMs;

  return (
    <section aria-labelledby="wrist-sensor" className={cn(look.card, look.pad, "flex flex-col gap-4")}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h3 id="wrist-sensor" className={look.title}>
          Wrist sensor
        </h3>
        <Badge variant="outline" className="h-5 rounded-full font-mono tracking-wide">
          MEASURED (sensor)
        </Badge>
        {series.mock && (
          <Badge variant="outline" className="h-5 rounded-full border-amber-400/50 text-amber-300">
            MOCK sensor data
          </Badge>
        )}
        <div className="ml-auto">
          <VerdictBadge verdict={verdict} />
        </div>
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">
        A phone strapped to the forearm measured these. The camera can&apos;t see the wrist roll.
      </p>

      <dl className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-3">
        <Stat
          label="Wrist speed at contact"
          value={formatRate(speedAtContact)}
          detail="Forearm turn rate at contact (gyro)"
          tag={tag}
        />
        <Stat
          label="Roll through contact"
          value={formatDeg(series.rollChangeDeg)}
          detail={`Forearm roll from ${formatMs(w0)} to ${formatMs(w1)}`}
          tag={tag}
        />
        {rollRate !== null && (
          <Stat
            label="Peak roll rate"
            value={formatRate(rollRate)}
            detail="Fastest roll about the forearm, the coach's reading"
            tag={tagFor(series.mock || coachSensor?.source === "mock sensor")}
          />
        )}
      </dl>

      <WristChart series={series} />

      {explanation && <p className="text-xs text-pretty text-muted-foreground">{explanation}</p>}

      <WristTable series={series} />
    </section>
  );
}

function Stat({ label, value, detail, tag }: { label: string; value: string; detail: string; tag: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-2xl border bg-(--media) p-4">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn(look.title, look.value, "text-2xl")}>{value}</dd>
      <dd className="text-xs text-muted-foreground">{detail}</dd>
      <dd className="mt-1 font-mono text-[0.65rem] tracking-wide text-muted-foreground">{tag}</dd>
    </div>
  );
}

// ---- chart -------------------------------------------------------------------------------

type Scale = { domain: [number, number]; ticks: number[] };

/** Axis range and round tick values for drawing. Display only: no number shown comes from here. */
function niceScale(values: number[], zeroBase: boolean): Scale {
  const lo = Math.min(0, ...values);
  let hi = Math.max(0, ...values);
  if (hi - lo < 1) hi = lo + 1;
  const pad = (hi - lo) * 0.08;
  const domain: [number, number] = [zeroBase ? lo : lo - pad, hi + pad];
  const raw = (domain[1] - domain[0]) / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const ticks: number[] = [];
  for (let v = Math.ceil(domain[0] / step) * step; v <= domain[1]; v += step) ticks.push(Math.round(v * 1000) / 1000 + 0);
  return { domain, ticks };
}

const pct = (v: number, [a, b]: [number, number]) => ((v - a) / (b - a)) * 100;

function linePath(points: { t: number; value: number | null }[], x: [number, number], y: [number, number]): string {
  let d = "";
  let drawing = false;
  for (const p of points) {
    if (p.value === null) {
      drawing = false;
      continue;
    }
    d += `${drawing ? "L" : "M"}${pct(p.t, x).toFixed(2)} ${(100 - pct(p.value, y)).toFixed(2)} `;
    drawing = true;
  }
  return d.trim();
}

const X_TICKS = [-300, -200, -100, 0, 100, 200];

function WristChart({ series }: { series: WristSeries }) {
  const readoutId = useId();
  const plotRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);

  const xDomain: [number, number] = [series.roll[0].t, series.roll[series.roll.length - 1].t];
  const rate = series.turnRate?.filter((p) => p.t >= xDomain[0] && p.t <= xDomain[1]) ?? null;
  // The readout stops where both series have a sample, so it lists both (else every roll sample).
  const rollTimes = series.roll.map((p) => p.t);
  const shared = rate ? rollTimes.filter((t) => rate.some((r) => r.t === t)) : [];
  const stops = shared.length > 0 ? shared : rollTimes;
  const at = hover ?? 0;
  const rollAt = sampleAt(series.roll, at);
  const rateAt = sampleAt(rate, at);

  function nearestStop(t: number): number {
    return stops.reduce((best, s) => (Math.abs(s - t) < Math.abs(best - t) ? s : best), stops[0]);
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const box = plotRef.current?.getBoundingClientRect();
    if (!box || box.width === 0) return;
    const f = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
    setHover(nearestStop(xDomain[0] + f * (xDomain[1] - xDomain[0])));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const i = stops.indexOf(nearestStop(at));
    const move: Record<string, number> = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: stops.length - 1 };
    if (event.key === "Escape") {
      setHover(null);
      return;
    }
    if (!(event.key in move)) return;
    event.preventDefault();
    setHover(stops[Math.min(Math.max(move[event.key], 0), stops.length - 1)]);
  }

  const rollScale = niceScale(
    series.roll.map((p) => p.value),
    false,
  );
  const rateValues = (rate ?? []).flatMap((p) => (p.value === null ? [] : [p.value]));
  const rateScale = rateValues.length > 0 ? niceScale(rateValues, true) : null;

  return (
    <div className="flex flex-col gap-2">
      <p id={readoutId} aria-live="polite" className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs text-muted-foreground tabular-nums">
        <span className="font-medium text-foreground">{hover === null ? "At contact" : formatMs(at)}</span>
        <span>
          Roll angle <span className="font-medium text-foreground">{formatDeg(rollAt)}</span>
        </span>
        {rate && (
          <span>
            Turn rate <span className="font-medium text-foreground">{formatRate(rateAt)}</span>
          </span>
        )}
      </p>
      <div
        role="group"
        tabIndex={0}
        aria-label="Roll angle and turn rate around contact. Left and right arrow keys step through the samples."
        aria-describedby={readoutId}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHover(null)}
        onFocus={() => setHover((h) => h ?? (stops.includes(0) ? 0 : stops[0]))}
        onBlur={() => setHover(null)}
        onKeyDown={onKeyDown}
        className="flex touch-pan-y flex-col gap-3 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <Plot
          title="Roll angle (°)"
          points={series.roll}
          x={xDomain}
          scale={rollScale}
          windowMs={series.windowMs}
          hover={hover}
          plotRef={plotRef}
          marker={{ t: series.windowMs[1], label: formatDeg(sampleAt(series.roll, series.windowMs[1])) }}
          formatTick={(v) => whole.format(v)}
          windowLabel
        />
        {rate && rateScale && (
          <Plot
            title="Turn rate (°/s)"
            points={rate}
            x={xDomain}
            scale={rateScale}
            windowMs={series.windowMs}
            hover={hover}
            marker={{ t: 0, label: formatRate(sampleAt(rate, 0)) }}
            formatTick={(v) => whole.format(v)}
          />
        )}
        <XAxis x={xDomain} />
      </div>
    </div>
  );
}

function Plot({
  title,
  points,
  x,
  scale,
  windowMs,
  hover,
  marker,
  formatTick,
  plotRef,
  windowLabel = false,
}: {
  title: string;
  points: { t: number; value: number | null }[];
  x: [number, number];
  scale: Scale;
  windowMs: [number, number];
  hover: number | null;
  /** The one value labelled on the line. */
  marker: { t: number; label: string };
  formatTick: (v: number) => string;
  plotRef?: Ref<HTMLDivElement>;
  windowLabel?: boolean;
}) {
  const y = scale.domain;
  const point = (t: number) => {
    const v = sampleAt(points, t);
    return v === null || t < x[0] || t > x[1] ? null : { left: pct(t, x), top: 100 - pct(v, y) };
  };
  const mark = point(marker.t);
  const hovered = hover === null ? null : point(hover);
  const w0 = Math.max(windowMs[0], x[0]);
  const w1 = Math.min(windowMs[1], x[1]);

  return (
    <div className="flex flex-col gap-1">
      <p className="pl-11 text-xs text-muted-foreground">{title}</p>
      <div className="grid grid-cols-[2.75rem_minmax(0,1fr)]">
        <div aria-hidden className="relative">
          {scale.ticks.map((tick) => (
            <span
              key={tick}
              className="absolute right-2 -translate-y-1/2 text-[0.65rem] text-muted-foreground tabular-nums"
              style={{ top: `${100 - pct(tick, y)}%` }}
            >
              {formatTick(tick)}
            </span>
          ))}
        </div>
        <div ref={plotRef} className="relative h-24">
          <svg aria-hidden viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 size-full overflow-visible">
            {w1 > w0 && (
              <rect x={pct(w0, x)} width={pct(w1, x) - pct(w0, x)} y={0} height={100} className="fill-foreground/[0.06]" />
            )}
            {scale.ticks.map((tick) => (
              <line
                key={tick}
                x1={0}
                x2={100}
                y1={100 - pct(tick, y)}
                y2={100 - pct(tick, y)}
                className="stroke-border"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            {0 >= x[0] && 0 <= x[1] && (
              <line
                x1={pct(0, x)}
                x2={pct(0, x)}
                y1={0}
                y2={100}
                className="stroke-muted-foreground"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            )}
            {hover !== null && (
              <line
                x1={pct(hover, x)}
                x2={pct(hover, x)}
                y1={0}
                y2={100}
                className="stroke-foreground/60"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path
              d={linePath(points, x, y)}
              fill="none"
              stroke={YOU_COLOUR}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          {windowLabel && w1 > w0 && (
            <span
              aria-hidden
              className="absolute top-1 pl-1 text-[0.65rem] text-muted-foreground"
              style={{ left: `${pct(w0, x)}%` }}
            >
              measured window
            </span>
          )}
          {mark && (
            <>
              <Dot left={mark.left} top={mark.top} />
              <span
                aria-hidden
                className="absolute ml-2.5 -translate-y-1/2 rounded bg-card/85 px-1 text-xs font-medium whitespace-nowrap text-foreground tabular-nums"
                style={{ left: `${mark.left}%`, top: `${mark.top}%` }}
              >
                {marker.label}
              </span>
            </>
          )}
          {hovered && <Dot left={hovered.left} top={hovered.top} />}
        </div>
      </div>
    </div>
  );
}

/** A 10px dot in the series colour with a 2px ring in the card colour, so it reads over any line. */
function Dot({ left, top }: { left: number; top: number }) {
  return (
    <span
      aria-hidden
      className="pointer-events-none absolute size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card"
      style={{ left: `${left}%`, top: `${top}%`, backgroundColor: YOU_COLOUR }}
    />
  );
}

/** Shared time axis. The unit sits once in the gutter, so six labels fit at phone width. */
function XAxis({ x }: { x: [number, number] }) {
  return (
    <div aria-hidden className="grid grid-cols-[2.75rem_minmax(0,1fr)]">
      <span className="pr-2 text-right text-[0.65rem] text-muted-foreground">ms</span>
      <div className="relative h-4">
        {X_TICKS.filter((t) => t >= x[0] && t <= x[1]).map((t, i, all) => (
          <span
            key={t}
            className={cn(
              "absolute text-[0.65rem] whitespace-nowrap tabular-nums",
              t === 0 ? "font-medium text-foreground" : "text-muted-foreground",
              i === 0 ? "" : i === all.length - 1 ? "-translate-x-full" : "-translate-x-1/2",
            )}
            style={{ left: `${pct(t, x)}%` }}
          >
            {t === 0 ? "contact" : `${t < 0 ? "−" : "+"}${Math.abs(t)}`}
          </span>
        ))}
      </div>
    </div>
  );
}

/** The same numbers as the chart, for anyone who can't use it. */
function WristTable({ series }: { series: WristSeries }) {
  return (
    <details className="group text-sm">
      <summary className="w-fit cursor-pointer rounded text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
        Show the numbers
      </summary>
      <div className="mt-2 max-h-64 overflow-auto rounded-lg border">
        <table className="w-full text-left text-xs tabular-nums">
          <caption className="sr-only">Forearm roll and turn rate around contact, measured by the wrist sensor</caption>
          <thead className="sticky top-0 bg-card text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-1.5 font-medium">
                Time from contact
              </th>
              <th scope="col" className="px-3 py-1.5 font-medium">
                Roll angle
              </th>
              {series.turnRate && (
                <th scope="col" className="px-3 py-1.5 font-medium">
                  Turn rate
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y">
            {series.roll.map((p) => (
              <tr key={p.t} className={cn(p.t === 0 && "font-medium text-foreground")}>
                <th scope="row" className="px-3 py-1 font-normal">
                  {formatMs(p.t)}
                </th>
                <td className="px-3 py-1">{formatDeg(p.value)}</td>
                {series.turnRate && <td className="px-3 py-1">{formatRate(sampleAt(series.turnRate, p.t))}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
