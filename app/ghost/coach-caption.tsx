// Coach caption laid over the 3D view, like a subtitle: the top fault, its cue and, when the
// ghost shows a different fix, the coach's ghost_note. Orange = what the player did (the
// fault), cyan = the fix (the cue). Once the coach's voice (#60) loads, its cue replaces the
// plain one, with a play button when there's audio and "worded by Claude" when Claude wrote it.
// The clip stops when the caption goes.

import { useEffect, useRef, useState } from "react";
import { RotateCcw, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import type { CoachCaption, CoachVoice } from "./compare";

export type CaptionState =
  | { kind: "loading" }
  | { kind: "error"; message: string; onRetry: () => void }
  | {
      kind: "ready";
      caption: CoachCaption;
      /** The spoken cue, once it has loaded. Null or absent: the plain caption. */
      voice?: CoachVoice | null;
    };

/** "Stance 80 deg open" -> "Stance 80° open". Wording only; the number is the file's. */
export function tidyLabel(label: string): string {
  return label.replace(/(\d) deg\b/g, "$1°");
}

export function CoachCaptionBar({ state, size }: { state: CaptionState; size: "large" | "compact" }) {
  const large = size === "large";
  return (
    <div className="pointer-events-none absolute inset-x-3 bottom-3 flex justify-center">
      <figure
        className={cn(
          "w-full max-w-3xl rounded-xl border bg-background/92 text-center shadow-lg",
          large ? "px-4 py-3 sm:px-6 sm:py-4" : "px-3 py-2 sm:px-5 sm:py-2.5",
          state.kind === "error" && "pointer-events-auto",
        )}
        aria-live="polite"
      >
        <figcaption className="text-[0.7rem] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
          Coach&apos;s call
          {state.kind === "ready" && state.caption.fault && (
            <span className="font-normal tracking-normal normal-case"> · {state.caption.fault.confidence} confidence</span>
          )}
        </figcaption>
        {state.kind === "loading" && <p className="mt-1 text-sm text-muted-foreground">Reading the coach&apos;s call…</p>}
        {state.kind === "error" && (
          <div className="mt-1 flex flex-wrap items-center justify-center gap-x-3 gap-y-2">
            <p className="text-sm text-muted-foreground">The coach&apos;s call didn&apos;t load: {state.message}</p>
            <Button variant="outline" size="sm" onClick={state.onRetry}>
              <RotateCcw data-icon="inline-start" />
              Try again
            </Button>
          </div>
        )}
        {state.kind === "ready" && (
          <>
            <p
              className={cn("mt-1 font-medium text-balance", large ? "text-lg sm:text-2xl" : "text-sm sm:text-base")}
              style={{ color: YOU_COLOUR }}
            >
              {state.caption.fault ? tidyLabel(state.caption.fault.label) : "No fault found"}
            </p>
            <blockquote
              className={cn(
                "mt-1 leading-tight font-semibold text-balance",
                large ? "text-2xl sm:text-4xl" : "text-lg sm:text-2xl",
              )}
              style={{ color: GHOST_COLOUR }}
            >
              “{state.voice?.cue ?? state.caption.cue}”
            </blockquote>
            {state.voice && (state.voice.audioUrl || state.voice.wordedByClaude) && (
              <div className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
                {state.voice.audioUrl && <PlayVoice url={state.voice.audioUrl} large={large} />}
                {state.voice.wordedByClaude && <span className="text-xs text-muted-foreground">worded by Claude</span>}
              </div>
            )}
            {state.caption.ghostNote && (
              <p className={cn("mt-1.5 text-balance text-muted-foreground", large ? "text-sm sm:text-base" : "text-xs sm:text-sm")}>
                {state.caption.ghostNote}
              </p>
            )}
          </>
        )}
      </figure>
    </div>
  );
}

/** The clip playing now, from any caption, so a new play stops it instead of talking over it. */
let playing: HTMLAudioElement | null = null;

/** Stops a clip and lets the browser drop it (an inline data: clip can be hundreds of KB). */
function release(audio: HTMLAudioElement) {
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (playing === audio) playing = null;
}

function PlayVoice({ url, large }: { url: string; large: boolean }) {
  const [busy, setBusy] = useState(false);
  /** This button's latest clip. */
  const clip = useRef<HTMLAudioElement | null>(null);

  // The button is going (back to the swing list, another swing, leaving /ghost): stop and release
  // its clip. Next can keep /ghost alive in the background, which runs this cleanup but keeps
  // state, hence the reset.
  useEffect(
    () => () => {
      if (clip.current) release(clip.current);
      clip.current = null;
      setBusy(false);
    },
    [],
  );

  function play() {
    if (playing) release(playing);
    const audio = new Audio(url);
    playing = audio;
    clip.current = audio;
    // An older clip stopping fires these too; only the latest one resets the button.
    const done = () => {
      if (clip.current === audio) setBusy(false);
    };
    audio.addEventListener("ended", done);
    audio.addEventListener("pause", done);
    audio.addEventListener("error", done);
    setBusy(true);
    // A clip the browser can't play stays quiet: the cue is on screen anyway.
    audio.play().catch(done);
  }

  return (
    <Button type="button" variant="outline" size={large ? "sm" : "xs"} className="pointer-events-auto" onClick={play}>
      <Volume2 data-icon="inline-start" />
      {busy ? "Playing…" : "Hear the coach"}
    </Button>
  );
}
