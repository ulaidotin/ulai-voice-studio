"use client";

import { Check, ChevronRight, Wrench, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { AgentState, CallEvent } from "@/lib/types";
import { cn, elapsedLabel } from "@/lib/utils";

function Bubble({ speaker, text, time, interim }: { speaker: string; text: string; time?: string; interim?: boolean }) {
  const agent = speaker === "agent";
  return (
    <div className={cn("flex animate-fade-in flex-col gap-1", agent ? "items-start" : "items-end")}>
      <div className="flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
        <span className="font-medium">{agent ? "Agent" : "Caller"}</span>
        {time && <span className="tabular-nums">{time}</span>}
      </div>
      <div
        className={cn(
          "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
          agent ? "rounded-tl-sm bg-muted" : "rounded-tr-sm bg-primary text-primary-foreground",
          interim && "opacity-60",
        )}
      >
        {text}
        {interim && <span className="ml-0.5 inline-block animate-pulse-soft">▍</span>}
      </div>
    </div>
  );
}

function ToolCard({ event, compact }: { event: CallEvent; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const data = event.data as { arguments?: unknown; result?: unknown; duration_ms?: number; ok?: boolean };
  const ok = data.ok !== false;
  if (compact) {
    return (
      <div className="flex justify-center">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[11px]",
            ok ? "text-muted-foreground" : "border-danger/40 text-danger",
          )}
        >
          <Wrench className="size-3" /> {event.text}
          {ok ? <Check className="size-3 text-success" /> : <X className="size-3" />}
        </span>
      </div>
    );
  }
  return (
    <div className="mx-auto w-full max-w-[85%] rounded-lg border bg-surface-2/60 text-sm">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <Wrench className="size-3.5 text-muted-foreground" />
        <span className="font-mono text-[13px]">{event.text}</span>
        <span className={cn("text-xs", ok ? "text-success" : "text-danger")}>{ok ? "succeeded" : "failed"}</span>
        {data.duration_ms !== undefined && (
          <span className="text-xs tabular-nums text-muted-foreground">{data.duration_ms} ms</span>
        )}
        <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">{elapsedLabel(event.elapsed_ms)}</span>
        <ChevronRight className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-90")} />
      </button>
      {open && (
        <div className="grid gap-2 border-t px-3 py-2.5 sm:grid-cols-2">
          {(["arguments", "result"] as const).map((k) => (
            <div key={k} className="min-w-0">
              <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{k}</div>
              <pre className="max-h-48 overflow-auto rounded-md bg-surface p-2 font-mono text-xs leading-relaxed">
                {JSON.stringify(data[k] ?? {}, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusLine({ event }: { event: CallEvent }) {
  return (
    <div className="flex items-center gap-3 py-1 text-[11px] text-muted-foreground">
      <div className="h-px flex-1 bg-border" />
      <span>{event.text}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}

const STATE_LABEL: Record<AgentState, string> = {
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
};

/** The conversation: transcript bubbles, tool calls and status changes, following new lines as they arrive. */
export function Timeline({
  events,
  interim,
  agentState,
  compact,
  empty,
  className,
}: {
  events: CallEvent[];
  interim?: { speaker: string; text: string } | null;
  agentState?: AgentState | null;
  compact?: boolean;
  empty?: React.ReactNode;
  className?: string;
}) {
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    if (pinned.current) end.current?.scrollIntoView({ block: "end" });
  }, [events.length, interim?.text]);

  const visible = compact ? events.filter((e) => e.kind !== "status" || /ended|failed|answer/i.test(e.text)) : events;

  return (
    <div
      ref={box}
      onScroll={(e) => {
        const el = e.currentTarget;
        pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}
      className={cn("space-y-3 overflow-y-auto", className)}
      aria-live="polite"
    >
      {visible.length === 0 && !interim ? (
        empty
      ) : (
        <>
          {visible.map((e) =>
            e.kind === "transcript" ? (
              <Bubble key={e.seq} speaker={e.speaker} text={e.text} time={elapsedLabel(e.elapsed_ms)} />
            ) : e.kind === "tool_call" ? (
              <ToolCard key={e.seq} event={e} compact={compact} />
            ) : (
              <StatusLine key={e.seq} event={e} />
            ),
          )}
          {interim && interim.text.trim() && <Bubble speaker={interim.speaker} text={interim.text} interim />}
        </>
      )}
      {agentState && (
        <div className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
          <span className="flex gap-0.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className={cn("size-1 rounded-full bg-current", agentState !== "listening" && "animate-pulse-soft")}
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </span>
          Agent: {STATE_LABEL[agentState]}
        </div>
      )}
      <div ref={end} />
    </div>
  );
}
