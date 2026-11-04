"use client";

import { ChevronLeft, ChevronRight, Download, Phone, PhoneCall, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { CallTable } from "@/components/calls/call-table";
import { Page, PageHeader } from "@/components/shell/app-shell";
import { useUI } from "@/components/shell/ui-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Empty, ErrorState } from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api, errorMessage } from "@/lib/api";
import { useAgents, useCalls } from "@/lib/queries";
import { DIRECTION_LABEL, STATUS_LABEL } from "@/lib/utils";

const PAGE_SIZE = 25;

function CallsView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { placeCall } = useUI();
  const agents = useAgents();

  // Filters live in the URL so a filtered view can be bookmarked or shared.
  const filters = {
    status: params.get("status") ?? "",
    direction: params.get("direction") ?? "",
    agent_id: params.get("agent_id") ?? "",
    q: params.get("q") ?? "",
  };
  const page = Math.max(1, Number(params.get("page")) || 1);
  const [search, setSearch] = useState(filters.q);

  function setParams(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }

  // Debounce the search box into the URL.
  useEffect(() => {
    if (search === filters.q) return;
    const t = setTimeout(() => setParams({ q: search.trim() }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const calls = useCalls({ ...filters, page, page_size: PAGE_SIZE });
  const total = calls.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filtered = Object.values(filters).some(Boolean);

  return (
    <Page>
      <PageHeader
        title="Calls"
        description="Every web, inbound and outbound call, with transcripts."
        actions={
          <>
            <Button asChild>
              <a href={api.exportUrl(filters)} download>
                <Download /> Export CSV
              </a>
            </Button>
            <Button variant="primary" onClick={() => placeCall()}>
              <Phone /> Place call
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Number, agent or call ID"
            className="pl-8"
            aria-label="Search calls"
          />
        </div>
        <Select
          className="w-[150px]"
          value={filters.status}
          onValueChange={(status) => setParams({ status })}
          options={[
            { value: "", label: "Any status" },
            ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          className="w-[150px]"
          value={filters.direction}
          onValueChange={(direction) => setParams({ direction })}
          options={[
            { value: "", label: "Any direction" },
            ...Object.entries(DIRECTION_LABEL).map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          className="w-[180px]"
          value={filters.agent_id}
          onValueChange={(agent_id) => setParams({ agent_id })}
          options={[{ value: "", label: "Any agent" }, ...(agents.data ?? []).map((a) => ({ value: a.id, label: a.name }))]}
        />
        {filtered && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearch("");
              router.replace(pathname, { scroll: false });
            }}
          >
            <X /> Clear
          </Button>
        )}
      </div>

      <Card className="overflow-hidden">
        {calls.isError ? (
          <ErrorState message={errorMessage(calls.error)} onRetry={() => calls.refetch()} />
        ) : calls.data && calls.data.items.length === 0 ? (
          filtered ? (
            <Empty icon={Search} title="No matching calls" description="Try different filters or clear them." />
          ) : (
            <Empty
              icon={PhoneCall}
              title="No calls yet"
              description="Test an agent from your browser, place a phone call, or route a number to an agent."
              action={
                <Button variant="primary" onClick={() => placeCall()}>
                  <Phone /> Place a call
                </Button>
              }
            />
          )
        ) : (
          <CallTable calls={calls.data?.items} loading={calls.isLoading} />
        )}
        {total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-sm">
            <span className="text-muted-foreground tabular-nums">
              {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total.toLocaleString()}
            </span>
            <div className="flex gap-1">
              <Button
                size="icon-sm"
                disabled={page <= 1}
                onClick={() => setParams({ page: String(page - 1) })}
                aria-label="Previous page"
              >
                <ChevronLeft />
              </Button>
              <Button
                size="icon-sm"
                disabled={page >= pages}
                onClick={() => setParams({ page: String(page + 1) })}
                aria-label="Next page"
              >
                <ChevronRight />
              </Button>
            </div>
          </div>
        )}
      </Card>
    </Page>
  );
}

export default function CallsPage() {
  return (
    <Suspense>
      <CallsView />
    </Suspense>
  );
}
