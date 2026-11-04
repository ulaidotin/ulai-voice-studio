"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { Skeleton } from "@/components/ui/skeleton";
import type { Call } from "@/lib/types";
import { cn, formatDuration, formatPhone, timeAgo } from "@/lib/utils";
import { DirectionLabel, StatusBadge } from "./status";

function counterpart(c: Call): string {
  if (c.direction === "web") return "Browser";
  return formatPhone(c.direction === "outbound" ? c.to_number : c.from_number) || "Unknown";
}

/** Calls as a table on wide screens and stacked rows on phones. Rows open the call. */
export function CallTable({ calls, loading, compact }: { calls?: Call[]; loading?: boolean; compact?: boolean }) {
  const router = useRouter();

  if (loading && !calls) {
    return (
      <div className="divide-y">
        {Array.from({ length: compact ? 5 : 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-3">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-36" />
            <Skeleton className="ml-auto h-4 w-16" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      <table className="hidden w-full text-sm md:table">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="px-4 py-2 font-medium">Contact</th>
            <th className="px-4 py-2 font-medium">Agent</th>
            <th className="px-4 py-2 font-medium">Direction</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 text-right font-medium">Duration</th>
            <th className="px-4 py-2 text-right font-medium">When</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {calls?.map((c) => (
            <tr
              key={c.id}
              onClick={() => router.push(`/calls/${c.id}`)}
              className="cursor-pointer transition-colors hover:bg-surface-2"
            >
              <td className="px-4 py-2.5">
                <Link
                  href={`/calls/${c.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="font-medium tabular-nums hover:underline"
                >
                  {counterpart(c)}
                </Link>
              </td>
              <td className="max-w-48 truncate px-4 py-2.5 text-muted-foreground">{c.agent_name || "—"}</td>
              <td className="px-4 py-2.5">
                <DirectionLabel direction={c.direction} />
              </td>
              <td className="px-4 py-2.5">
                <StatusBadge status={c.status} />
              </td>
              <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                {formatDuration(c.duration_seconds)}
              </td>
              <td className="whitespace-nowrap px-4 py-2.5 text-right text-muted-foreground" title={c.created_at}>
                {timeAgo(c.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="divide-y md:hidden">
        {calls?.map((c) => (
          <li key={c.id}>
            <Link href={`/calls/${c.id}`} className={cn("flex items-center gap-3 px-4 py-3 hover:bg-surface-2")}>
              <DirectionLabel direction={c.direction} iconOnly />
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium tabular-nums">{counterpart(c)}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {c.agent_name} · {timeAgo(c.created_at)}
                </div>
              </div>
              <StatusBadge status={c.status} />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}
