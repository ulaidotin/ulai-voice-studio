"use client";

import { useQuery } from "@tanstack/react-query";

import { api, type CallFilters } from "./api";
import { isActive } from "./types";

export const keys = {
  me: ["me"] as const,
  overview: ["overview"] as const,
  health: ["health"] as const,
  catalog: ["catalog"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  trunks: ["trunks"] as const,
  callsRoot: ["calls", "list"] as const,
  calls: (f: CallFilters & { page: number; page_size: number }) => ["calls", "list", f] as const,
  call: (id: string) => ["calls", "detail", id] as const,
};

export const useMe = () => useQuery({ queryKey: keys.me, queryFn: api.me, staleTime: 5 * 60_000 });
export const useOverview = () => useQuery({ queryKey: keys.overview, queryFn: api.overview });
export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 60_000, staleTime: 30_000 });
export const useCatalog = () => useQuery({ queryKey: keys.catalog, queryFn: api.catalog, staleTime: Infinity });
export const useAgents = () => useQuery({ queryKey: keys.agents, queryFn: api.agents });
export const useAgent = (id: string) => useQuery({ queryKey: keys.agent(id), queryFn: () => api.agent(id) });
export const useTrunks = () => useQuery({ queryKey: keys.trunks, queryFn: api.trunks });

export const useCalls = (f: CallFilters & { page: number; page_size: number }) =>
  useQuery({ queryKey: keys.calls(f), queryFn: () => api.calls(f), placeholderData: (prev) => prev });

export const useCall = (id: string) =>
  useQuery({
    queryKey: keys.call(id),
    queryFn: () => api.call(id),
    // Live updates arrive over SSE; this is a safety net in case the stream drops.
    refetchInterval: (q) => (q.state.data && isActive(q.state.data.status) ? 15_000 : false),
  });
