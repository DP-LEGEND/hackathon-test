// The clip: a big drop target until one is chosen, then the chosen clip with a preview. Drops are
// caught anywhere on the page (upload-form.tsx); `dragging` lights this up while a file is over it.
// Orange = what the player did, so the player's own clip is marked in orange.

import { useCallback, useRef, useState } from "react";
import { FileVideo, X } from "lucide-react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { YOU_COLOUR } from "../ghost/colours";
import { CLIP_ACCEPT, MAX_CLIP_BYTES, formatBytes } from "./process-clip";

export function ClipDrop({
  file,
  dragging,
  disabled,
  error,
  onPick,
  onClear,
}: {
  file: File | null;
  dragging: boolean;
  disabled: boolean;
  /** Why the last file picked can't be used, or null. */
  error: string | null;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const highlight = dragging && !disabled;
  const lit = highlight
    ? { borderColor: YOU_COLOUR, backgroundColor: `color-mix(in oklch, ${YOU_COLOUR} 8%, transparent)` }
    : undefined;
  const choose = () => inputRef.current?.click();

  return (
    <section aria-labelledby="clip-heading" className="upload-clip-card">
      <h2 id="clip-heading" className="upload-card-title">
        Your video
      </h2>
      <input
        ref={inputRef}
        type="file"
        accept={CLIP_ACCEPT}
        hidden
        onChange={(event) => {
          const picked = event.target.files?.[0];
          event.target.value = ""; // so picking the same file again still counts
          if (picked) onPick(picked);
        }}
      />
      {file ? (
        <div
          className={cn(
            "upload-selected flex flex-col gap-4 rounded-2xl border bg-card p-3 transition-colors sm:flex-row sm:items-center sm:p-4",
            highlight && "border-dashed",
          )}
          style={lit}
        >
          <ClipPreview key={`${file.name}:${file.size}:${file.lastModified}`} file={file} />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p
              className="flex items-center gap-2 text-xs font-semibold tracking-[0.14em] uppercase"
              style={{ color: YOU_COLOUR }}
            >
              <span aria-hidden className="size-2 rounded-full" style={{ backgroundColor: YOU_COLOUR }} />
              Your swing
            </p>
            <p className="truncate text-base font-medium" title={file.name}>
              {file.name}
            </p>
            <p className="text-sm text-muted-foreground tabular-nums">
              {highlight ? "Drop to use the new video instead" : formatBytes(file.size)}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={disabled} onClick={choose}>
                Choose another
              </Button>
              <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={onClear}>
                <X data-icon="inline-start" />
                Remove
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div
          className={cn(
            "upload-dropzone flex flex-col items-center gap-4 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors sm:py-14",
            !highlight && "bg-card/40",
          )}
          style={lit}
        >
          <span
            aria-hidden
            className="upload-symbol"
          >
            <Image src="/upload/upload.svg" width={40} height={40} alt="" />
          </span>
          <div className="flex flex-col gap-1">
            <p className="text-lg font-medium text-balance">
              {highlight ? "Drop to use this video" : "Drop your swing video here"}
            </p>
            <p className="text-sm text-muted-foreground">
              MOV, MP4, M4V or AVI · up to {formatBytes(MAX_CLIP_BYTES)}
            </p>
          </div>
          <Button type="button" variant="ghost" size="lg" className="upload-browse" disabled={disabled} onClick={choose}>
            <FileVideo data-icon="inline-start" />
            Choose a video
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}

/** The chosen clip, playable when this browser can decode it (an iPhone HEVC .mov may not be). */
function ClipPreview({ file }: { file: File }) {
  const [playable, setPlayable] = useState(true);
  // A fresh object URL each time the video is attached, revoked when it's detached.
  const attach = useCallback(
    (video: HTMLVideoElement | null) => {
      if (!video) return;
      const url = URL.createObjectURL(file);
      video.src = `${url}#t=0.1`; // show a frame, not black, before it plays
      return () => URL.revokeObjectURL(url);
    },
    [file],
  );

  return (
    <div className="aspect-video w-full shrink-0 overflow-hidden rounded-xl bg-black sm:w-56">
      {playable ? (
        <video
          ref={attach}
          aria-label={`Preview of ${file.name}`}
          className="size-full object-contain"
          controls
          muted
          playsInline
          preload="metadata"
          onError={() => setPlayable(false)}
          onLoadedMetadata={(event) => {
            if (event.currentTarget.videoWidth === 0) setPlayable(false);
          }}
        />
      ) : (
        <div className="flex size-full flex-col items-center justify-center gap-2 p-3 text-center text-muted-foreground">
          <FileVideo aria-hidden className="size-6" />
          <p className="text-xs text-pretty">No preview in this browser. That’s fine: the service decodes it itself.</p>
        </div>
      )}
    </div>
  );
}
