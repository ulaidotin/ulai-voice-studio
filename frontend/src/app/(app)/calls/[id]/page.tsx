"use client";

import { ArrowLeft, Bot, Copy, MessageSquareText, PhoneOff } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { toast } from "sonner";

import { DirectionLabel, StatusBadge } from "@/components/calls/status";
import { Timeline } from "@/components/calls/timeline";
import { Page } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Confirm } from "@/components/ui/confirm";
import { Empty, ErrorState } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError, errorMessage } from "@/lib/api";
import { applyCall, useLiveCall } from "@/lib/live";
import { useCall } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";
import type { CallDetail } from "@/lib/types";
import { isActive } from "@/lib/types";
import { clock, dateTime, formatDuration, formatPhone } from "@/lib/utils";

function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate text-sm">{children}</dd>
    </div>
  );
}

function LiveClock({ since }: { since: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return <span className="font-mono tabular-nums">{clock((now - new Date(since).getTime()) / 1000)}</span>;
}

function Header({ call }: { call: CallDetail }) {
  const qc = useQueryClient();
  const active = isActive(call.status);
  const title =
    call.direction === "web"
      ? "Web call"
      : formatPhone(call.direction === "outbound" ? call.to_number : call.from_number) || "Phone call";
  const tokens = (call.usage.prompt_tokens ?? 0) + (call.usage.response_tokens ?? 0);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b px-4 py-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold tabular-nums tracking-tight">{title}</h1>
            <StatusBadge status={call.status} />
            {active && call.answered_at && (
              <span className="text-sm text-success">
                <LiveClock since={call.answered_at} />
              </span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <DirectionLabel direction={call.direction} />
            <span>·</span>
            {call.agent_id ? (
              <Link href={`/agents/${call.agent_id}`} className="inline-flex items-center gap-1 hover:text-foreground">
                <Bot className="size-3.5" /> {call.agent_name}
              </Link>
            ) : (
              <span className="inline-flex items-center gap-1">
                <Bot className="size-3.5" /> {call.agent_name || "Deleted agent"}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              void navigator.clipboard?.writeText(call.id);
              toast.success("Call ID copied");
            }}
          >
            <Copy /> ID
          </Button>
          {active && (
            <Confirm
              title="End this call?"
              description="The agent and the other party are disconnected immediately."
              confirmLabel="End call"
              trigger={
                <Button size="sm" variant="danger">
                  <PhoneOff /> End call
                </Button>
              }
              onConfirm={async () => {
                try {
                  applyCall(qc, await api.endCall(call.id));
                } catch (err) {
                  toast.error(errorMessage(err));
                }
              }}
            />
          )}
        </div>
      </div>
      <dl className="grid grid-cols-2 gap-4 px-4 py-4 sm:grid-cols-3 lg:grid-cols-6">
        <Meta label="From">{call.direction === "web" ? "Browser" : formatPhone(call.from_number) || "—"}</Meta>
        <Meta label="To">{call.direction === "web" ? "Agent" : formatPhone(call.to_number) || "—"}</Meta>
        <Meta label="Started">{dateTime(call.created_at)}</Meta>
        <Meta label="Duration">{active ? "In progress" : formatDuration(call.duration_seconds)}</Meta>
        <Meta label="Ended because">
          <span title={call.end_reason}>{call.end_reason || (active ? "—" : "Unknown")}</span>
        </Meta>
        <Meta label="Tokens">{tokens ? tokens.toLocaleString() : "—"}</Meta>
      </dl>
      {call.error && (
        <div className="border-t bg-danger-soft/50 px-4 py-2.5 text-sm text-danger">{call.error}</div>
      )}
      {Object.keys(call.variables).length > 0 && (
        <div className="flex flex-wrap gap-2 border-t px-4 py-3 text-xs">
          {Object.entries(call.variables).map(([k, v]) => (
            <span key={k} className="rounded-md bg-muted px-2 py-1">
              <span className="font-mono text-muted-foreground">{k}</span> = {v}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function CallPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const call = useCall(id);
  const active = call.data ? isActive(call.data.status) : false;
  const live = useLiveCall(id, active);

  return (
    <Page className="max-w-4xl">
      <Button variant="ghost" size="sm" asChild className="-ml-2">
        <Link href="/calls">
          <ArrowLeft /> Calls
        </Link>
      </Button>

      {call.isError ? (
        <Card>
          <ErrorState
            message={
              call.error instanceof ApiError && call.error.status === 404
                ? "This call doesn't exist."
                : errorMessage(call.error)
            }
            onRetry={() => call.refetch()}
          />
        </Card>
      ) : !call.data ? (
        <>
          <Skeleton className="h-44 w-full rounded-lg" />
          <Skeleton className="h-96 w-full rounded-lg" />
        </>
      ) : (
        <>
          <Header call={call.data} />
          <Card>
            <CardHeader
              title="Conversation"
              description={active ? "Live: new lines appear as they're spoken" : undefined}
            />
            <Timeline
              className="max-h-[70dvh] px-4 py-4"
              events={call.data.events}
              interim={live.interim}
              agentState={active ? live.agentState : null}
              empty={
                <Empty
                  icon={MessageSquareText}
                  title={active ? "Waiting for the conversation to start" : "Nothing was said"}
                  className="py-10"
                />
              }
            />
          </Card>
        </>
      )}
    </Page>
  );
}
