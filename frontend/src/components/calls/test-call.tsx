"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Loader2, Mic, MicOff, Phone, PhoneOff, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Room } from "ulai-js-sdk";

import { PoweredBy } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, errorMessage } from "@/lib/api";
import { useLiveCall } from "@/lib/live";
import { keys } from "@/lib/queries";
import type { AgentIn, Variable } from "@/lib/types";
import { isActive } from "@/lib/types";
import { clock, cn } from "@/lib/utils";
import { Timeline } from "./timeline";

type Phase = "idle" | "connecting" | "live" | "ended" | "error";

const DISCONNECT_GRACE_MS = 10_000;

function micError(err: unknown): string {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "Microphone access is blocked. Allow it in your browser's site settings, then try again.";
  if (name === "NotFoundError") return "No microphone was found. Connect one and try again.";
  if (name === "NotReadableError") return "Your microphone is in use by another app.";
  return errorMessage(err);
}

/** Ends a call even while the page is unloading. */
function endInBackground(callId: string) {
  void fetch(`/api/calls/${callId}/end`, { method: "POST", keepalive: true, credentials: "same-origin" }).catch(
    () => undefined,
  );
}

/** Talk to an agent from the browser over Ulai Voice Infra, with a live transcript. */
export function TestCall({
  agentId,
  agentName,
  variables,
  className,
  draft,
}: {
  agentId: string;
  agentName: string;
  variables: Variable[];
  className?: string;
  /** Unsaved edits: the call runs on these instead of the saved agent. */
  draft?: AgentIn;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [liveSince, setLiveSince] = useState<number | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});

  const room = useRef<Room | null>(null);
  const audio = useRef<HTMLAudioElement>(null);
  const meter = useRef<HTMLDivElement>(null);
  const stopMeter = useRef<() => void>(() => undefined);
  const activeCall = useRef<string | null>(null);

  const detail = useQuery({
    queryKey: keys.call(callId ?? ""),
    queryFn: () => api.call(callId!),
    enabled: !!callId,
  });
  // The call can also end on the server: the agent hangs up, or the maximum duration is reached.
  const serverEnded = phase === "live" && !!detail.data && !isActive(detail.data.status);
  const view: Phase = serverEnded ? "ended" : phase;
  const live = useLiveCall(callId, view === "live" || view === "connecting");

  const teardown = useCallback(() => {
    stopMeter.current();
    stopMeter.current = () => undefined;
    const r = room.current;
    room.current = null;
    if (r) {
      r.removeAllListeners();
      r.disconnect();
    }
    if (audio.current) audio.current.srcObject = null;
  }, []);

  const finish = useCallback(
    (next: Phase, message?: string) => {
      if (activeCall.current) {
        endInBackground(activeCall.current);
        activeCall.current = null;
      }
      teardown();
      setPhase(next);
      if (message) setError(message);
    },
    [teardown],
  );

  // Leaving the page or closing the panel hangs up.
  useEffect(() => {
    const onUnload = () => activeCall.current && endInBackground(activeCall.current);
    window.addEventListener("pagehide", onUnload);
    return () => {
      window.removeEventListener("pagehide", onUnload);
      onUnload();
      activeCall.current = null;
      teardown();
    };
  }, [teardown]);

  // The call timer.
  useEffect(() => {
    if (view !== "live" || liveSince === null) return;
    const t = setInterval(() => setElapsed((Date.now() - liveSince) / 1000), 500);
    return () => clearInterval(t);
  }, [view, liveSince]);

  // Release the mic and connection once the server has ended the call.
  useEffect(() => {
    if (!serverEnded) return;
    activeCall.current = null;
    teardown();
  }, [serverEnded, teardown]);

  function startMeter(stream: MediaStream) {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new Ctx();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    let raf = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (const v of data) sum += ((v - 128) / 128) ** 2;
      const level = Math.min(1, Math.sqrt(sum / data.length) * 4);
      if (meter.current) meter.current.style.transform = `scaleX(${level})`;
      raf = requestAnimationFrame(tick);
    };
    tick();
    stopMeter.current = () => {
      cancelAnimationFrame(raf);
      void ctx.close();
    };
  }

  async function start() {
    setError(null);
    setMuted(false);
    setCallId(null);
    setPhase("connecting");

    // Ask for the mic before creating the call: the join ticket expires in ~30s,
    // and a permission prompt left open would run it out.
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((t) => t.stop());
    } catch (err) {
      setPhase("error");
      setError(micError(err));
      return;
    }

    let res;
    try {
      const vars = Object.fromEntries(Object.entries(values).filter(([, v]) => v.trim() !== ""));
      res = await api.startWebCall(agentId, vars, draft);
    } catch (err) {
      setPhase("error");
      setError(errorMessage(err));
      return;
    }
    activeCall.current = res.call_id;
    setCallId(res.call_id);

    const r = new Room(res.control_plane_url);
    room.current = r;
    r.on("trackSubscribed", (_track: MediaStreamTrack, stream: MediaStream) => {
      if (audio.current) {
        audio.current.srcObject = stream;
        void audio.current.play().catch(() => undefined);
      }
    });
    r.on("sessionTerminated", () => finish("ended"));
    // "disconnected" also fires on brief network drops that WebRTC recovers from, so give it a moment.
    // A call the server really ended shows up through the call's live status instead.
    let lost: ReturnType<typeof setTimeout> | undefined;
    const recovered = () => clearTimeout(lost);
    r.on("connected", recovered);
    r.on("reconnected", recovered);
    r.on("disconnected", () => {
      clearTimeout(lost);
      lost = setTimeout(() => {
        if (room.current === r) finish("error", "The connection dropped and didn't recover.");
      }, DISCONNECT_GRACE_MS);
    });

    try {
      await r.connect({
        roomId: res.session_id,
        participantId: res.participant_id,
        ticket: res.ticket,
        nodeAddress: res.node_address,
        eventsToken: res.events_token ?? undefined,
        iceServers: res.ice_servers,
      });
      const stream = await r.publishAudio();
      startMeter(stream);
      setElapsed(0);
      setLiveSince(Date.now());
      setPhase("live");
    } catch (err) {
      finish("error", micError(err));
    }
  }

  function hangUp() {
    if (activeCall.current) {
      // Await the end so the call page shows the final state, but don't block the UI on it.
      const id = activeCall.current;
      activeCall.current = null;
      void api.endCall(id).catch(() => endInBackground(id));
    }
    teardown();
    setPhase("ended");
  }

  function toggleMute() {
    const next = !muted;
    room.current?.setMuted(next);
    setMuted(next);
  }

  const events = detail.data?.events ?? [];
  const inCall = view === "connecting" || view === "live";

  return (
    <div className={cn("flex h-full min-h-0 flex-col", className)}>
      <audio ref={audio} autoPlay playsInline className="hidden" />

      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold">Test call</div>
          <div className="truncate text-xs text-muted-foreground">Talk to {agentName} from your browser</div>
        </div>
        {view === "live" && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2 py-0.5 font-mono text-xs tabular-nums text-success">
            <span className="size-1.5 animate-pulse-soft rounded-full bg-current" /> {clock(elapsed)}
          </span>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {view === "idle" || view === "error" ? (
          <div className="flex h-full flex-col overflow-y-auto p-4">
            <div className="flex flex-1 flex-col items-center justify-center py-6 text-center">
              <div className="relative mb-4 flex size-16 items-center justify-center rounded-full bg-primary-soft text-primary">
                <Phone className="size-6" />
              </div>
              <p className="max-w-64 text-sm text-muted-foreground">
                Your browser will ask to use the microphone. Speak naturally; you can interrupt the agent.
              </p>
              {error && (
                <p className="mt-4 max-w-72 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
                  {error}
                </p>
              )}
            </div>
            {variables.length > 0 && (
              <fieldset className="mb-4 space-y-3 rounded-lg border p-3">
                <legend className="px-1 text-xs font-medium text-muted-foreground">Variables for this call</legend>
                {variables.map((v) => (
                  <Field key={v.name} label={<span className="font-mono text-xs">{`{{${v.name}}}`}</span>} hint={v.description}>
                    <Input
                      value={values[v.name] ?? ""}
                      placeholder={v.default ? `Default: ${v.default}` : undefined}
                      onChange={(e) => setValues({ ...values, [v.name]: e.target.value })}
                    />
                  </Field>
                ))}
              </fieldset>
            )}
            <Button variant="primary" size="lg" className="w-full" onClick={start}>
              <Phone /> {view === "error" ? "Try again" : "Start call"}
            </Button>
            {draft && (
              <p className="mt-2 text-center text-xs text-muted-foreground">Uses your unsaved changes.</p>
            )}
          </div>
        ) : (
          <Timeline
            className="h-full px-4 py-4"
            events={events}
            interim={live.interim}
            agentState={view === "live" ? live.agentState : null}
            compact
            empty={
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                {view === "connecting" ? (
                  <>
                    <Loader2 className="size-5 animate-spin" /> Connecting to {agentName}…
                  </>
                ) : view === "live" ? (
                  "Connected. Say hello."
                ) : (
                  "Nothing was said."
                )}
              </div>
            }
          />
        )}
      </div>

      {inCall && (
        <div className="flex items-center gap-3 border-t px-4 py-3">
          <Button
            size="icon"
            variant={muted ? "danger" : "secondary"}
            onClick={toggleMute}
            disabled={view !== "live"}
            aria-pressed={muted}
            aria-label={muted ? "Unmute" : "Mute"}
          >
            {muted ? <MicOff /> : <Mic />}
          </Button>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" aria-hidden>
            <div
              ref={meter}
              className={cn("h-full origin-left rounded-full bg-success transition-transform duration-75", muted && "opacity-30")}
              style={{ transform: "scaleX(0)" }}
            />
          </div>
          <Button variant="danger" onClick={hangUp}>
            <PhoneOff /> End
          </Button>
        </div>
      )}

      {view === "ended" && (
        <div className="flex items-center gap-2 border-t px-4 py-3">
          <Button variant="primary" onClick={start} className="flex-1">
            <RotateCcw /> Call again
          </Button>
          {callId && (
            <Button asChild>
              <Link href={`/calls/${callId}`}>
                Details <ArrowUpRight />
              </Link>
            </Button>
          )}
        </div>
      )}

      <div className="flex justify-center border-t py-2">
        <PoweredBy />
      </div>
    </div>
  );
}
