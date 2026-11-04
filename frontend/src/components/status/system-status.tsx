"use client";

import { CheckCircle2, CircleAlert, CircleDashed, RefreshCw, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Level = "ok" | "warn" | "error" | "idle";

const ICON = { ok: CheckCircle2, warn: CircleAlert, error: XCircle, idle: CircleDashed };
const COLOR = { ok: "text-success", warn: "text-warning", error: "text-danger", idle: "text-muted-foreground" };

function Row({ level, title, detail }: { level: Level; title: string; detail: React.ReactNode }) {
  const Icon = ICON[level];
  return (
    <li className="flex gap-3 px-4 py-3">
      <Icon className={cn("mt-0.5 size-4 shrink-0", COLOR[level])} />
      <div className="min-w-0">
        <div className="text-sm font-medium">{title}</div>
        <div className="mt-0.5 break-words text-xs text-muted-foreground">{detail}</div>
      </div>
    </li>
  );
}

const code = "rounded bg-muted px-1 py-0.5 font-mono text-[11px] text-foreground";

/** What the studio needs to work, and what to do about anything missing. */
export function SystemStatus({ className }: { className?: string }) {
  const health = useHealth();
  const h = health.data;

  return (
    <Card className={className}>
      <CardHeader
        title="System status"
        description="Connection to Ulai Voice Infra and the AI credentials"
        action={
          <Button
            size="icon-sm"
            variant="ghost"
            onClick={() => health.refetch()}
            aria-label="Check again"
            disabled={health.isFetching}
          >
            <RefreshCw className={cn(health.isFetching && "animate-spin")} />
          </Button>
        }
      />
      {!h ? (
        health.isError ? (
          <p className="px-4 py-4 text-sm text-danger">Couldn&apos;t load the status.</p>
        ) : (
          <div className="space-y-3 p-4">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )
      ) : (
        <ul className="divide-y">
          <Row
            level={h.ulai === "ok" ? "ok" : "error"}
            title="Ulai Voice Infra"
            detail={
              h.ulai === "ok" ? (
                <>
                  Connected · project <span className={code}>{h.project_id}</span>
                </>
              ) : h.ulai === "unconfigured" ? (
                <>
                  Set <span className={code}>ULAI_API_KEY</span> in the server&apos;s <span className={code}>.env</span>{" "}
                  and restart it.
                </>
              ) : (
                h.ulai_detail || "Can't reach Ulai."
              )
            }
          />
          <Row
            level={h.google_credentials ? "ok" : "error"}
            title="Gemini credentials"
            detail={
              h.google_credentials ? (
                "Google service account loaded"
              ) : (
                <>
                  Add the service account key as <span className={code}>credentials/google-service-account.json</span>{" "}
                  on the server. Agents can&apos;t talk without it.
                </>
              )
            }
          />
          <Row
            level={h.inbound_listener === "running" ? "ok" : h.inbound_listener === "error" ? "warn" : "idle"}
            title="Inbound calls"
            detail={
              h.inbound_listener === "running"
                ? "Listening for calls to your inbound numbers"
                : h.inbound_listener === "error"
                  ? "The inbound listener lost its connection and is retrying."
                  : "Idle. Assign an agent to an inbound trunk to answer calls."
            }
          />
        </ul>
      )}
    </Card>
  );
}
