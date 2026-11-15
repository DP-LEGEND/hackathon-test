// Optional settings sent with the clip. Auto leaves the field out, so the service works it out
// (services/pipeline/README.md, "Film one clip live"); anything picked here overrides it.

import { useId } from "react";
import { cn } from "@/lib/utils";
import type { ClipSettings, Hand, Slowdown, Stroke } from "./process-clip";

type Option<T extends string> = { value: T; label: string };

const HANDS: Option<Hand>[] = [
  { value: "auto", label: "Auto" },
  { value: "R", label: "Right" },
  { value: "L", label: "Left" },
];

const STROKES: Option<Stroke>[] = [
  { value: "auto", label: "Auto" },
  { value: "forehand", label: "Forehand" },
  { value: "backhand", label: "Backhand" },
];

const SLOWDOWNS: Option<Slowdown>[] = [
  { value: "auto", label: "Auto" },
  { value: "1", label: "1×" },
  { value: "4", label: "4×" },
  { value: "8", label: "8×" },
];

const SLOWDOWN_HINTS: Record<Slowdown, string> = {
  auto: "Auto reads the clip’s timing. Slow-motion clips often need it set.",
  "1": "Normal-speed video, such as 60 fps.",
  "4": "Plays 4× slower than real life, such as 120 fps slow motion played at 30 fps.",
  "8": "Plays 8× slower than real life, such as 240 fps slow motion played at 30 fps.",
};

export function ClipSettingsPanel({
  value,
  onChange,
  disabled,
}: {
  value: ClipSettings;
  onChange: (next: ClipSettings) => void;
  disabled: boolean;
}) {
  return (
    <section aria-labelledby="settings-heading" className="upload-settings flex flex-col gap-4 rounded-2xl border bg-card/60 p-4 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="settings-heading" className="text-base font-medium">
          Settings
        </h2>
        <p className="text-sm text-muted-foreground">Optional · Auto works for most clips</p>
      </div>
      <fieldset disabled={disabled} className="flex min-w-0 flex-col gap-4">
        <legend className="sr-only">Settings for this clip</legend>
        <Segmented
          label="Hitting hand"
          name="hand"
          options={HANDS}
          value={value.hand}
          onChange={(hand) => onChange({ ...value, hand })}
        />
        <Segmented
          label="Stroke"
          name="stroke"
          options={STROKES}
          value={value.stroke}
          onChange={(stroke) => onChange({ ...value, stroke })}
        />
        <Segmented
          label="Slowdown"
          name="slowdown"
          options={SLOWDOWNS}
          value={value.slowdown}
          onChange={(slowdown) => onChange({ ...value, slowdown })}
          hint={SLOWDOWN_HINTS[value.slowdown]}
        />
      </fieldset>
    </section>
  );
}

/** One setting as a row of native radios styled as a segmented control (arrow keys move between them). */
function Segmented<T extends string>({
  label,
  name,
  options,
  value,
  onChange,
  hint,
}: {
  label: string;
  name: string;
  options: Option<T>[];
  value: T;
  onChange: (next: T) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="upload-setting grid gap-2 sm:grid-cols-[8rem_minmax(0,1fr)] sm:items-start">
      <span id={`${id}-label`} className="text-sm font-medium sm:pt-1.5">
        {label}
      </span>
      <div className="flex min-w-0 flex-col gap-1.5">
        <div
          role="radiogroup"
          aria-labelledby={`${id}-label`}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className="upload-segments flex w-full rounded-lg border bg-background/60 p-0.5 sm:w-fit"
        >
          {options.map((option) => (
            <label key={option.value} className="relative flex-1 sm:flex-none">
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={value === option.value}
                onChange={() => onChange(option.value)}
                className="peer sr-only"
              />
              <span
                className={cn(
                  "flex min-h-11 cursor-pointer items-center justify-center rounded-md px-3 text-sm whitespace-nowrap text-muted-foreground transition-colors select-none peer-enabled:hover:text-foreground",
                  "peer-checked:bg-secondary peer-checked:text-foreground peer-checked:shadow-sm",
                  "peer-focus-visible:ring-3 peer-focus-visible:ring-ring/50",
                  "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
                )}
              >
                {option.label}
              </span>
            </label>
          ))}
        </div>
        {hint && (
          <p id={`${id}-hint`} className="text-xs text-pretty text-muted-foreground">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}
