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

export function AskCoach({ sessionKey, tools }: { sessionKey: string; tools: Record<string, CoachTool> }) {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let live = true;
    fetch("/api/coach/agent", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((data: unknown) => {
        if (live) setAvailable(typeof data === "object" && data !== null && (data as { available?: unknown }).available === true);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
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
      onMessage={({ message, role }) => add({ who: role === "user" ? "You" : "Coach", text: message })}
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
      // stripAudioTags: keep expressive tags like "[curious]" out of the transcript.
      conversation.startSession({ signedUrl, stripAudioTags: true });
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
