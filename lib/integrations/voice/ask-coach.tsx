"use client";

// "Ask the coach": a real-time ElevenLabs voice agent (Agents SDK) for follow-up questions about
// one swing. Hidden unless the service says it's configured (GET /api/coach/agent). The browser
// never sees the key: it asks our service for a signed URL (POST /api/coach/agent/session).
// The agent's tools run here, on data the swing view already loaded (app/ghost/ask-coach-tools.ts).

import { useEffect, useMemo, useRef, useState } from "react";
import { ConversationProvider, useConversation } from "@elevenlabs/react";
import { Mic, PhoneOff, SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type CoachTool = (parameters: Record<string, unknown>) => Promise<unknown>;
type Line = { who: "You" | "Coach"; text: string };

// stripAudioTags misses hyphenated tags such as "[matter-of-fact]"; drop those from the transcript too.
const withoutTags = (text: string) => text.replace(/\[[\p{L}\p{M}\p{N}_\s'-]+\](?!\()/gu, "").replace(/\s{2,}/g, " ").trim();

// Waits before re-asking when the availability check failed (service down or starting).
const RECHECK_MS = [2_000, 5_000, 10_000, 30_000];

export function AskCoach({
  sessionKey,
  tools,
  recheck = 0,
}: {
  sessionKey: string;
  tools: Record<string, CoachTool>;
  /** Change it (e.g. the page's API "Try again" counter) to ask the service again now. */
  recheck?: number;
}) {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let live = true;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Only the service's answer settles it: {"available": false} keeps the panel hidden for good.
    // A failed request (network error, proxy 502) retries quietly, so the panel can appear
    // once the service is up, without a page reload.
    const check = () => {
      fetch("/api/coach/agent", { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json() as Promise<unknown>;
        })
        .then((data) => {
          if (live) setAvailable(typeof data === "object" && data !== null && (data as { available?: unknown }).available === true);
        })
        .catch(() => {
          if (live) timer = setTimeout(check, RECHECK_MS[Math.min(failures++, RECHECK_MS.length - 1)]);
        });
    };
    check();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [recheck]);
  if (!available) return null;
  // Keyed by swing: a new swing starts a new conversation.
  return <AskCoachSession key={sessionKey} tools={tools} />;
}

function AskCoachSession({ tools }: { tools: Record<string, CoachTool> }) {
  const toolsRef = useRef(tools);
  useEffect(() => {
    toolsRef.current = tools;
  }, [tools]);
  const [names] = useState(() => Object.keys(tools));
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState<string | null>(null);
  const clientTools = useMemo(
    () =>
      Object.fromEntries(
        names.map((name) => [
          name,
          async (parameters: unknown) => {
            try {
              const args = typeof parameters === "object" && parameters !== null ? (parameters as Record<string, unknown>) : {};
              return JSON.stringify(await toolsRef.current[name](args));
            } catch (cause) {
              return JSON.stringify({ error: cause instanceof Error ? cause.message : String(cause) });
            }
          },
        ]),
      ),
    [names],
  );
  const add = (line: Line) => setLines((previous) => [...previous, line].slice(-8));
  return (
    <ConversationProvider
      clientTools={clientTools}
      onMessage={({ message, role }) => add({ who: role === "user" ? "You" : "Coach", text: role === "user" ? message : withoutTags(message) })}
      onError={(message: unknown) => setError(typeof message === "string" ? message : "The coach couldn't connect.")}
    >
      <AskCoachPanel lines={lines} error={error} setError={setError} onTyped={(text) => add({ who: "You", text })} />
    </ConversationProvider>
  );
}

function AskCoachPanel({
  lines,
  error,
  setError,
  onTyped,
}: {
  lines: Line[];
  error: string | null;
  setError: (e: string | null) => void;
  /** Typed questions aren't echoed back by the agent, so the transcript adds them here. */
  onTyped: (text: string) => void;
}) {
  const conversation = useConversation();
  const [draft, setDraft] = useState("");
  const [starting, setStarting] = useState(false);
  const connected = conversation.status === "connected";

  async function start() {
    setError(null);
    setStarting(true);
    try {
      const response = await fetch("/api/coach/agent/session", { method: "POST", cache: "no-store" });
      const data: unknown = response.ok ? await response.json() : null;
      const signedUrl = typeof data === "object" && data !== null ? (data as { signedUrl?: unknown }).signedUrl : null;
      if (typeof signedUrl !== "string") throw new Error("The coach isn't available right now.");
      // The SDK's startSession returns nothing and reports a failed start (microphone denied,
      // handshake failed) through onError, so wait for this attempt to connect or fail; the button
      // stays on "Connecting…" until then. These callbacks run alongside the provider's own.
      await new Promise<void>((resolve, reject) => {
        conversation.startSession({
          signedUrl,
          // Keep expressive tags like "[curious]" out of the transcript.
          stripAudioTags: true,
          onConnect: () => resolve(),
          onDisconnect: () => resolve(),
          onError: (message: string) =>
            reject(new Error(`The coach couldn't start${message ? ` (${message})` : ""}. Allow the microphone and try again.`)),
        });
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The coach isn't available right now.");
    } finally {
      setStarting(false);
    }
  }

  function send() {
    const text = draft.trim();
    if (!text || !connected) return;
    conversation.sendUserMessage(text);
    onTyped(text);
    setDraft("");
  }

  return (
    <section aria-label="Ask the coach" className="flex flex-col gap-3 rounded-[20px] border bg-(--panel) p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        {connected ? (
          <Button variant="outline" className="rounded-full px-4" onClick={() => conversation.endSession()}>
            <PhoneOff data-icon="inline-start" />
            End
          </Button>
        ) : (
          <Button className="rounded-full px-4" disabled={starting || conversation.status === "connecting"} onClick={start}>
            <Mic data-icon="inline-start" />
            {starting || conversation.status === "connecting" ? "Connecting…" : "Ask the coach"}
          </Button>
        )}
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {connected
            ? conversation.isSpeaking
              ? "The coach is speaking"
              : "Listening: ask why, or what you should feel"
            : "Talk to the coach about this swing. It quotes only numbers the code measured; ball paths are PREDICTED."}
        </p>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {lines.length > 0 && (
        <ol className="flex flex-col gap-1.5 text-sm" aria-label="Conversation">
          {lines.map((line, index) => (
            <li key={index}>
              <span className="font-semibold">{line.who}:</span> {line.text}
            </li>
          ))}
        </ol>
      )}
      {connected && (
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <Input
            aria-label="Type a question for the coach"
            placeholder="Or type a question"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <Button type="submit" variant="outline" aria-label="Send">
            <SendHorizontal />
          </Button>
        </form>
      )}
    </section>
  );
}
