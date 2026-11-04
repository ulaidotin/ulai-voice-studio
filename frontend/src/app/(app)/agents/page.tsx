"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, Copy, MoreHorizontal, Phone, PhoneIncoming, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Page, PageHeader } from "@/components/shell/app-shell";
import { useUI } from "@/components/shell/ui-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Confirm } from "@/components/ui/confirm";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Empty, ErrorState } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { emptyAgent } from "@/lib/agent-defaults";
import { api, errorMessage } from "@/lib/api";
import { keys, useAgents, useCatalog } from "@/lib/queries";
import type { AgentSummary } from "@/lib/types";
import { formatPhone, plural, timeAgo } from "@/lib/utils";

function AgentCard({ agent, languages }: { agent: AgentSummary; languages: Map<string, string> }) {
  const qc = useQueryClient();
  const router = useRouter();
  const { placeCall } = useUI();
  const [confirmDelete, setConfirmDelete] = useState(false);

  const duplicate = useMutation({
    mutationFn: () => api.duplicateAgent(agent.id),
    onSuccess: (copy) => {
      void qc.invalidateQueries({ queryKey: keys.agents });
      toast.success(`Created ${copy.name}`);
      router.push(`/agents/${copy.id}`);
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  return (
    <Card className="group relative flex flex-col transition-shadow hover:shadow-md">
      <Link
        href={`/agents/${agent.id}`}
        className="absolute inset-0 rounded-lg"
        aria-label={`Open ${agent.name}`}
      />
      <div className="flex items-start gap-3 p-4">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
          <Bot className="size-[18px]" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold">{agent.name}</h3>
          <p className="mt-0.5 line-clamp-2 min-h-8 text-xs text-muted-foreground">
            {agent.description || "No description"}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon-sm" variant="ghost" className="relative z-10 -mr-1.5 -mt-1" aria-label="Agent actions">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => placeCall(agent.id)}>
              <Phone /> Place a call
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => duplicate.mutate()} disabled={duplicate.isPending}>
              <Copy /> Duplicate
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem danger onSelect={() => setConfirmDelete(true)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="flex flex-wrap gap-1.5 px-4 pb-3">
        <Badge tone="outline">{agent.voice}</Badge>
        <Badge tone="outline">{languages.get(agent.language) ?? (agent.language || "Auto-detect")}</Badge>
        {agent.inbound_numbers.slice(0, 2).map((n) => (
          <Badge key={n} tone="primary">
            <PhoneIncoming /> {formatPhone(n)}
          </Badge>
        ))}
        {agent.inbound_numbers.length > 2 && <Badge tone="primary">+{agent.inbound_numbers.length - 2}</Badge>}
      </div>
      <div className="mt-auto flex items-center justify-between border-t px-4 py-2.5 text-xs text-muted-foreground">
        <span>{plural(agent.calls_last_7d, "call")} this week</span>
        <span>Edited {timeAgo(agent.updated_at)}</span>
      </div>
      <Confirm
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${agent.name}?`}
        description={
          agent.inbound_numbers.length
            ? `Its numbers (${agent.inbound_numbers.map(formatPhone).join(", ")}) will stop being answered. Call history is kept.`
            : "Call history is kept. This can't be undone."
        }
        onConfirm={async () => {
          try {
            await api.deleteAgent(agent.id);
            await qc.invalidateQueries({ queryKey: keys.agents });
            void qc.invalidateQueries({ queryKey: keys.trunks });
            toast.success(`Deleted ${agent.name}`);
          } catch (err) {
            toast.error(errorMessage(err));
          }
        }}
      />
    </Card>
  );
}

export default function AgentsPage() {
  const agents = useAgents();
  const catalog = useCatalog();
  const router = useRouter();
  const qc = useQueryClient();
  const languages = new Map((catalog.data?.languages ?? []).map((l) => [l.id, l.name]));

  const create = useMutation({
    mutationFn: () => api.createAgent(emptyAgent()),
    onSuccess: (agent) => {
      void qc.invalidateQueries({ queryKey: keys.agents });
      router.push(`/agents/${agent.id}`);
    },
    onError: (err) => toast.error(errorMessage(err)),
  });

  const newButton = (
    <Button variant="primary" onClick={() => create.mutate()} loading={create.isPending}>
      <Plus /> New agent
    </Button>
  );

  return (
    <Page>
      <PageHeader title="Agents" description="Each agent has its own prompt, voice and behaviour." actions={newButton} />
      {agents.isError ? (
        <Card>
          <ErrorState message={errorMessage(agents.error)} onRetry={() => agents.refetch()} />
        </Card>
      ) : agents.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-lg" />
          ))}
        </div>
      ) : agents.data?.length === 0 ? (
        <Card>
          <Empty
            icon={Bot}
            title="No agents yet"
            description="Create an agent, give it a prompt and a voice, and test it from your browser right away."
            action={newButton}
          />
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {agents.data?.map((a) => <AgentCard key={a.id} agent={a} languages={languages} />)}
        </div>
      )}
    </Page>
  );
}
