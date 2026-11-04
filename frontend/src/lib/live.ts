"use client";

import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { keys } from "./queries";
import type { AgentState, Call, CallDetail, CallPage, LiveMessage, Overview } from "./types";
import { isActive } from "./types";

/** Applies a call update everywhere the call is cached: its page, call lists and the overview. */
export function applyCall(qc: QueryClient, call: Call) {
  const before =
    qc.getQueryData<CallDetail>(keys.call(call.id))?.status ??
    qc
      .getQueriesData<CallPage>({ queryKey: keys.callsRoot })
      .flatMap(([, page]) => page?.items ?? [])
      .find((c) => c.id === call.id)?.status ??
    qc.getQueryData<Overview>(keys.overview)?.recent.find((c) => c.id === call.id)?.status;

  qc.setQueryData<CallDetail>(keys.call(call.id), (old) => (old ? { ...old, ...call } : old));
  qc.setQueriesData<CallPage>({ queryKey: keys.callsRoot }, (old) => {
    if (!old) return old;
    const i = old.items.findIndex((c) => c.id === call.id);
    if (i >= 0) {
      const items = old.items.slice();
      items[i] = call;
      return { ...old, items };
    }
    return old;
  });
  qc.setQueryData<Overview>(keys.overview, (old) => {
    if (!old) return old;
    const i = old.recent.findIndex((c) => c.id === call.id);
    const recent = i >= 0 ? old.recent.map((c) => (c.id === call.id ? call : c)) : [call, ...old.recent].slice(0, 8);
    return { ...old, recent };
  });
  // A new call or one changing state affects counts; refetch them in the background.
  if (before !== call.status) {
    void qc.invalidateQueries({ queryKey: keys.overview, refetchType: "active" });
  }
}

function subscribe(url: string, onMessage: (msg: LiveMessage) => void, onResume?: () => void): () => void {
  let source: EventSource | null = null;
  const open = () => {
    if (source) return;
    source = new EventSource(url);
    source.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data) as LiveMessage);
      } catch {
        // ignore malformed frames
      }
    };
    // EventSource reconnects by itself (the server sends `retry: 3000`).
  };
  const close = () => {
    source?.close();
    source = null;
  };
  // A page kept in the back/forward cache would otherwise keep its stream open. Over HTTP/1.1 browsers allow
  // only 6 connections per host, so a few cached pages are enough to stall every request the app makes.
  const onShow = (e: PageTransitionEvent) => {
    if (!e.persisted) return;
    open();
    onResume?.(); // updates sent while the page was cached were missed
  };
  open();
  window.addEventListener("pagehide", close);
  window.addEventListener("pageshow", onShow);
  return () => {
    window.removeEventListener("pagehide", close);
    window.removeEventListener("pageshow", onShow);
    close();
  };
}

/** Keeps call lists and the overview live. Mount once, in the app shell. */
export function useLiveCalls() {
  const qc = useQueryClient();
  useEffect(
    () =>
      subscribe("/api/calls/live", (msg) => {
        if (msg.type === "call") {
          const isNew =
            !qc.getQueryData(keys.call(msg.call.id)) &&
            !qc
              .getQueriesData<CallPage>({ queryKey: keys.callsRoot })
              .some(([, page]) => page?.items.some((c) => c.id === msg.call.id));
          applyCall(qc, msg.call);
          if (isNew) void qc.invalidateQueries({ queryKey: keys.callsRoot, refetchType: "active" });
        }
      }, () => void qc.invalidateQueries()),
    [qc],
  );
}

export interface LiveCallState {
  interim: { speaker: string; text: string } | null;
  agentState: AgentState | null;
}

/** Streams one call's transcript into its cached detail, plus what's being said right now. */
export function useLiveCall(callId: string | null, enabled = true): LiveCallState {
  const qc = useQueryClient();
  const [state, setState] = useState<LiveCallState>({ interim: null, agentState: null });

  useEffect(() => {
    if (!callId || !enabled) return;
    return subscribe(`/api/calls/${callId}/live`, (msg) => {
      if (msg.type === "event") {
        qc.setQueryData<CallDetail>(keys.call(callId), (old) => {
          if (!old || old.events.some((e) => e.seq === msg.event.seq)) return old;
          return { ...old, events: [...old.events, msg.event].sort((a, b) => a.seq - b.seq) };
        });
        if (msg.event.kind === "transcript") setState((s) => ({ ...s, interim: null }));
      } else if (msg.type === "interim") {
        setState((s) => ({ ...s, interim: { speaker: msg.speaker, text: msg.text } }));
      } else if (msg.type === "agent_state") {
        setState((s) => ({ ...s, agentState: msg.state }));
      } else if (msg.type === "call") {
        applyCall(qc, msg.call);
        if (!isActive(msg.call.status)) setState({ interim: null, agentState: null });
      }
    }, () => void qc.invalidateQueries({ queryKey: keys.call(callId) }));
  }, [callId, enabled, qc]);

  return state;
}
