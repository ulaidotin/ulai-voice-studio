"use client";

import { ArrowRight, Bot, Phone, PhoneCall, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { CallTable } from "@/components/calls/call-table";
import { Page, PageHeader } from "@/components/shell/app-shell";
import { useUI } from "@/components/shell/ui-context";
import { SystemStatus } from "@/components/status/system-status";
import { Dot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Empty, ErrorState } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api";
import { useOverview } from "@/lib/queries";
import type { DailyCount } from "@/lib/types";
import { cn, formatDuration } from "@/lib/utils";

function Stat({ label, value, hint, live }: { label: string; value: React.ReactNode; hint?: string; live?: boolean }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {live && <Dot pulse className="text-success" />}
        {label}
      </div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </Card>
  );
}

const SERIES = [
  { key: "web", label: "Web", color: "var(--color-chart-web)" },
  { key: "inbound", label: "Inbound", color: "var(--color-chart-inbound)" },
  { key: "outbound", label: "Outbound", color: "var(--color-chart-outbound)" },
] as const;

function CallsChart({ days }: { days: DailyCount[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const totals = days.map((d) => d.web + d.inbound + d.outbound);
  const max = Math.max(4, ...totals);
  const W = 640;
  const H = 180;
  const pad = { top: 8, bottom: 22, left: 28, right: 4 };
  const plotH = H - pad.top - pad.bottom;
  const slot = (W - pad.left - pad.right) / days.length;
  const barW = Math.min(36, slot * 0.56);
  const ticks = [0, Math.round(max / 2), max];

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-48 w-full" role="img" aria-label="Calls per day for the last 7 days">
        {ticks.map((t) => {
          const y = pad.top + plotH - (t / max) * plotH;
          return (
            <g key={t}>
              <line x1={pad.left} x2={W - pad.right} y1={y} y2={y} className="stroke-border" strokeDasharray="3 3" />
              <text x={pad.left - 6} y={y + 3} textAnchor="end" className="fill-muted-foreground text-[10px]">
                {t}
              </text>
            </g>
          );
        })}
        {days.map((d, i) => {
          const x = pad.left + i * slot + (slot - barW) / 2;
          let y = pad.top + plotH;
          const label = new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
          return (
            <g key={d.date} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={pad.left + i * slot} y={pad.top} width={slot} height={plotH} fill="transparent" />
              {SERIES.map((s) => {
                const h = (d[s.key] / max) * plotH;
                y -= h;
                return h > 0 ? (
                  <rect key={s.key} x={x} y={y} width={barW} height={h} rx={2} fill={s.color}
                    opacity={hover === null || hover === i ? 1 : 0.45} />
                ) : null;
              })}
              <text x={x + barW / 2} y={H - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      {hover !== null && days[hover] && (
        <div
          className="pointer-events-none absolute top-0 rounded-md border bg-surface px-2.5 py-1.5 text-xs shadow-md"
          style={{ left: `${((pad.left + (hover + 0.5) * slot) / W) * 100}%`, transform: "translateX(-50%)" }}
        >
          <div className="mb-1 font-medium">
            {new Date(`${days[hover].date}T00:00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" })}
          </div>
          {SERIES.map((s) => (
            <div key={s.key} className="flex items-center gap-2 tabular-nums">
              <span className="size-2 rounded-sm" style={{ background: s.color }} />
              <span className="text-muted-foreground">{s.label}</span>
              <span className="ml-auto pl-3 font-medium">{days[hover]![s.key]}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-1 flex gap-4 text-xs text-muted-foreground">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-sm" style={{ background: s.color }} /> {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function OverviewPage() {
  const { data, isLoading, isError, error, refetch } = useOverview();
  const { placeCall } = useUI();

  return (
    <Page>
      <PageHeader
        title="Overview"
        description="Your voice agents at a glance"
        actions={
          <>
            <Button onClick={() => placeCall()}>
              <Phone /> Place call
            </Button>
            <Button variant="primary" asChild>
              <Link href="/agents">
                <Bot /> Agents
              </Link>
            </Button>
          </>
        }
      />

      {isError ? (
        <Card>
          <ErrorState message={errorMessage(error)} onRetry={() => refetch()} />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            {isLoading || !data ? (
              Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-[86px] rounded-lg" />)
            ) : (
              <>
                <Stat label="Active now" value={data.active_calls} live={data.active_calls > 0} />
                <Stat label="Calls today" value={data.calls_today} />
                <Stat label="Last 7 days" value={data.calls_7d} />
                <Stat
                  label="Answer rate"
                  value={data.answer_rate_7d === null ? "—" : `${Math.round(data.answer_rate_7d * 100)}%`}
                  hint="Outbound, 7 days"
                />
                <Stat label="Avg duration" value={formatDuration(data.avg_duration_7d)} hint="7 days" />
                <Stat label="Talk time" value={`${data.total_minutes_7d}m`} hint="7 days" />
              </>
            )}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader title="Calls per day" description="Last 7 days, by direction" />
              <div className="px-4 pb-3 pt-4">
                {data ? <CallsChart days={data.daily} /> : <Skeleton className="h-52 w-full" />}
              </div>
            </Card>
            <SystemStatus />
          </div>

          <Card className="overflow-hidden">
            <CardHeader
              title="Recent calls"
              action={
                <Button variant="ghost" size="sm" asChild>
                  <Link href="/calls">
                    All calls <ArrowRight />
                  </Link>
                </Button>
              }
            />
            {data && data.recent.length === 0 ? (
              data.agents === 0 ? (
                <Empty
                  icon={Bot}
                  title="Create your first agent"
                  description="Write a prompt, pick a voice, and talk to it from your browser in under a minute."
                  action={
                    <Button variant="primary" asChild>
                      <Link href="/agents">
                        <Plus /> New agent
                      </Link>
                    </Button>
                  }
                />
              ) : (
                <Empty
                  icon={PhoneCall}
                  title="No calls yet"
                  description="Start a test call from an agent's page, or place a phone call."
                />
              )
            ) : (
              <div className={cn(!data && "min-h-40")}>
                <CallTable calls={data?.recent} loading={isLoading} compact />
              </div>
            )}
          </Card>
        </>
      )}
    </Page>
  );
}
