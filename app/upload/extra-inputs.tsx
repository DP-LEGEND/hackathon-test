// Optional inputs under the clip: a second camera angle of the same swing (for measured depth),
// with its time offset, and a wrist sensor export (.zip or .csv). Either file switches the upload to
// POST /api/process/multi (process-clip.ts); with neither, the upload is the usual /process.
// Each zone takes its own drops, so a file dropped here never replaces the main video.

import { useEffect, useId, useRef, useState, type DragEvent, type ElementType } from "react";
import { FileUp, FileVideo, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { YOU_COLOUR } from "../ghost/colours";
import {
  CLIP_ACCEPT,
  MAX_CLIP_BYTES,
  MAX_SENSOR_CSV_BYTES,
  MAX_SENSOR_ZIP_BYTES,
  SENSOR_ACCEPT,
  checkClip,
  checkOffset,
  checkSensorFile,
  formatBytes,
  wholeMegabytes,
  type ExtraInputs,
} from "./process-clip";

export function ExtraInputsPanel({
  value,
  onChange,
  disabled,
  onHover,
}: {
  value: ExtraInputs;
  onChange: (next: ExtraInputs) => void;
  disabled: boolean;
  /** A file is being dragged over one of these zones (so the main drop zone isn't lit). */
  onHover: (over: boolean) => void;
}) {
  const offsetId = useId();
  const offsetProblem = checkOffset(value.offset);
  return (
    <section aria-label="Optional inputs" className="upload-clip-card upload-extras">
      <ExtraDrop
        title="Second camera angle (optional, for measured depth)"
        icon={FileVideo}
        file={value.secondClip}
        accept={CLIP_ACCEPT}
        check={checkClip}
        prompt="Drop a second video of the same swing"
        formats={`MOV, MP4, M4V or AVI · up to ${formatBytes(MAX_CLIP_BYTES)} · uses the same Slowdown setting`}
        chooseLabel="Choose a second angle"
        disabled={disabled}
        onPick={(secondClip) => onChange({ ...value, secondClip })}
        onClear={() => onChange({ ...value, secondClip: null })}
        onHover={onHover}
      />
      <details className="upload-advanced">
        <summary>Advanced</summary>
        <div className="flex flex-col gap-1.5 pt-3">
          <label htmlFor={offsetId} className="text-sm font-medium">
            Second clip offset (s)
          </label>
          <Input
            id={offsetId}
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            value={value.offset}
            disabled={disabled}
            onChange={(event) => onChange({ ...value, offset: event.target.value })}
            aria-invalid={offsetProblem ? true : undefined}
            aria-describedby={`${offsetId}-hint`}
            className="upload-offset tabular-nums"
          />
          <p
            id={`${offsetId}-hint`}
            className={cn("text-xs text-pretty", offsetProblem ? "text-destructive" : "text-muted-foreground")}
          >
            {offsetProblem ?? "Leave empty unless the two clips need a manual time offset. Only used with a second camera angle."}
          </p>
        </div>
      </details>
      <ExtraDrop
        title="Wrist sensor export (.zip or .csv, optional)"
        icon={FileUp}
        file={value.sensorFile}
        accept={SENSOR_ACCEPT}
        check={checkSensorFile}
        prompt="Drop the Sensor Logger .zip or a .csv"
        formats={`ZIP up to ${wholeMegabytes(MAX_SENSOR_ZIP_BYTES)} · CSV up to ${wholeMegabytes(MAX_SENSOR_CSV_BYTES)}`}
        chooseLabel="Choose a ZIP or CSV"
        disabled={disabled}
        onPick={(sensorFile) => onChange({ ...value, sensorFile })}
        onClear={() => onChange({ ...value, sensorFile: null })}
        onHover={onHover}
      />
    </section>
  );
}

const hasFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");

function ExtraDrop({
  title,
  icon: Icon,
  file,
  accept,
  check,
  prompt,
  formats,
  chooseLabel,
  disabled,
  onPick,
  onClear,
  onHover,
}: {
  title: string;
  icon: ElementType<{ className?: string; "aria-hidden"?: boolean }>;
  file: File | null;
  accept: string;
  check: (file: File) => string | null;
  prompt: string;
  formats: string;
  chooseLabel: string;
  disabled: boolean;
  onPick: (file: File) => void;
  onClear: () => void;
  onHover: (over: boolean) => void;
}) {
  const headingId = useId();
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const lit = over && !disabled;
  const litStyle = lit
    ? { borderColor: YOU_COLOUR, backgroundColor: `color-mix(in oklch, ${YOU_COLOUR} 8%, transparent)` }
    : undefined;

  // Choosing or removing swaps the button that had focus for another, so focus follows to it.
  const chooseRef = useRef<HTMLButtonElement>(null);
  const removeRef = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);
  useEffect(() => {
    if (!refocus.current) return;
    refocus.current = false;
    (file ? removeRef : chooseRef).current?.focus();
  }, [file]);

  // As for the main clip, a rejected file also clears the one chosen before it.
  function take(next: File) {
    const problem = check(next);
    setError(problem);
    refocus.current = true;
    if (problem) onClear();
    else onPick(next);
  }

  // The picker uses an input made on demand, not one in the page: /upload keeps a single
  // <input type=file>, the main clip's.
  function choose() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.addEventListener("change", () => {
      const picked = input.files?.[0];
      if (picked) take(picked);
    });
    input.click();
  }

  function hover(next: boolean) {
    setOver(next);
    onHover(next);
  }

  // preventDefault marks the drop as handled, so the page-wide handler in upload-form.tsx leaves it.
  const dropTarget = {
    onDragEnter: (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth.current += 1;
      if (depth.current === 1) hover(true);
    },
    onDragOver: (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = disabled ? "none" : "copy";
    },
    onDragLeave: (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) hover(false);
    },
    onDrop: (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth.current = 0;
      hover(false);
      const next = event.dataTransfer.files[0];
      if (next && !disabled) take(next);
    },
  };

  return (
    <div role="group" aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="upload-card-title">
        {title}
      </h2>
      {file ? (
        <div {...dropTarget} className={cn("upload-extra-zone", lit && "border-dashed")} style={litStyle}>
          <Icon aria-hidden className="size-5 shrink-0 text-muted-foreground" />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="truncate text-sm font-medium" title={file.name}>
              {file.name}
            </p>
            <p className="text-xs text-muted-foreground tabular-nums">
              {lit ? "Drop to use the new file instead" : formatBytes(file.size)}
            </p>
          </div>
          <Button
            ref={removeRef}
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => {
              setError(null);
              refocus.current = true;
              onClear();
            }}
            aria-label={`Remove ${file.name}`}
          >
            <X data-icon="inline-start" />
            Remove
          </Button>
        </div>
      ) : (
        <div {...dropTarget} className="upload-extra-zone upload-extra-empty" style={litStyle}>
          <Icon aria-hidden className="size-5 shrink-0 text-muted-foreground" />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="text-sm font-medium text-pretty">{lit ? "Drop to use this file" : prompt}</p>
            <p className="text-xs text-muted-foreground">{formats}</p>
          </div>
          <Button
            ref={chooseRef}
            type="button"
            variant="ghost"
            size="sm"
            className="upload-browse"
            disabled={disabled}
            onClick={choose}
          >
            {chooseLabel}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
