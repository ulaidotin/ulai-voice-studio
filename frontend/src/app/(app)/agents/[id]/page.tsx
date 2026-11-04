"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Braces, Copy, MessagesSquare, MoreHorizontal, Phone, Settings2, Trash2, Wrench, Mic2, Headphones } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import {
  BehaviourSection,
  ConversationSection,
  VariablesSection,
  VoiceSection,
  type Errors,
} from "@/components/agents/sections";
import { ToolsSection } from "@/components/agents/tools";
import { TestCall } from "@/components/calls/test-call";
import { useUI } from "@/components/shell/ui-context";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Confirm } from "@/components/ui/confirm";
import { SheetContent } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { ErrorState } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toAgentIn } from "@/lib/agent-defaults";
import { api, ApiError, errorMessage } from "@/lib/api";
import { keys, useAgent, useCatalog } from "@/lib/queries";
import type { Agent, AgentIn } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

const SECTIONS = [
  { id: "behaviour", label: "Behaviour", icon: MessagesSquare, fields: ["prompt", "greeting", "closing", "opening"] },
  { id: "voice", label: "Voice & model", icon: Mic2, fields: ["voice", "model", "language", "temperature"] },
  {
    id: "conversation",
    label: "Conversation",
    icon: Settings2,
    fields: ["max_call_duration_seconds", "engagement_timeout_seconds"],
  },
  { id: "variables", label: "Variables", icon: Braces, fields: ["variables"] },
  { id: "tools", label: "Tools", icon: Wrench, fields: ["tools"] },
] as const;

/** Warns before leaving with unsaved changes: closing the tab, or following an in-app link. */
function useLeaveGuard(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const onUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    const onClick = (e: MouseEvent) => {
      const a = (e.target as HTMLElement | null)?.closest("a[href]");
      if (!a || a.getAttribute("target") === "_blank" || e.metaKey || e.ctrlKey) return;
      const href = a.getAttribute("href") ?? "";
      if (!href.startsWith("/") || href === window.location.pathname) return;
      if (!window.confirm("You have unsaved changes. Leave without saving?")) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", onUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);
}

function Editor({ agent }: { agent: Agent }) {
  const qc = useQueryClient();
  const router = useRouter();
  const catalog = useCatalog();
  const { placeCall } = useUI();
  const saved = useMemo(() => toAgentIn(agent), [agent]);
  const [draft, setDraft] = useState<AgentIn>(saved);
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState<string>("behaviour");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(saved), [draft, saved]);
  useLeaveGuard(dirty);

  const patch = (changes: Partial<AgentIn>) => {
    setDraft((d) => ({ ...d, ...changes }));
    // Clear errors for whatever was just edited.
    setErrors((e) => {
      const keysChanged = Object.keys(changes);
      return Object.fromEntries(Object.entries(e).filter(([k]) => !keysChanged.some((c) => k === c || k.startsWith(`${c}.`))));
    });
  };

  async function save() {
    setSaving(true);
    try {
      const updated = await api.updateAgent(agent.id, draft);
      qc.setQueryData(keys.agent(agent.id), updated);
      void qc.invalidateQueries({ queryKey: keys.agents });
      setDraft(toAgentIn(updated));
      setErrors({});
      toast.success("Saved");
    } catch (err) {
      if (err instanceof ApiError && err.fields.length) {
        const map: Errors = Object.fromEntries(err.fields.map((f) => [f.path.join(".") || "form", f.message]));
        setErrors(map);
        const top = String(err.fields[0]?.path[0] ?? "");
        const section = SECTIONS.find((s) => (s.fields as readonly string[]).includes(top));
        if (section) setTab(section.id);
        toast.error(err.message);
      } else {
        toast.error(errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  }

  // ⌘S saves.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (dirty && !saving) void save();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  async function duplicate() {
    try {
      const copy = await api.duplicateAgent(agent.id);
      void qc.invalidateQueries({ queryKey: keys.agents });
      router.push(`/agents/${copy.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const sectionErrors = (fields: readonly string[]) =>
    Object.keys(errors).some((k) => fields.some((f) => k === f || k.startsWith(`${f}.`)));

  const testCall = (
    <TestCall
      agentId={agent.id}
      agentName={draft.name || agent.name}
      variables={draft.variables.filter((v) => v.name)}
      draft={dirty ? draft : undefined}
    />
  );

  return (
    <div className="flex min-h-dvh">
      <div className="min-w-0 flex-1">
        <div className="mx-auto max-w-4xl px-4 pb-28 pt-5 md:px-8">
          <div className="flex items-center justify-between gap-2">
            <Button variant="ghost" size="sm" asChild className="-ml-2">
              <Link href="/agents">
                <ArrowLeft /> Agents
              </Link>
            </Button>
            <div className="flex items-center gap-2">
              <span className="hidden text-xs text-muted-foreground sm:inline">Saved {timeAgo(agent.updated_at)}</span>
              <Button size="sm" onClick={() => placeCall(agent.id)}>
                <Phone /> Place call
              </Button>
              <DialogPrimitive.Root open={sheetOpen} onOpenChange={setSheetOpen}>
                <DialogPrimitive.Trigger asChild>
                  <Button size="sm" variant="primary" className="xl:hidden">
                    <Headphones /> Test
                  </Button>
                </DialogPrimitive.Trigger>
                <SheetContent title="Test call">{sheetOpen && testCall}</SheetContent>
              </DialogPrimitive.Root>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="icon-sm" variant="ghost" aria-label="More actions">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onSelect={duplicate}>
                    <Copy /> Duplicate
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem danger onSelect={() => setConfirmDelete(true)}>
                    <Trash2 /> Delete agent
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          <div className="mt-4 space-y-1">
            <input
              value={draft.name}
              onChange={(e) => patch({ name: e.target.value })}
              className="-mx-1.5 w-full rounded-md bg-transparent px-1.5 py-0.5 text-2xl font-semibold tracking-tight outline-none hover:bg-accent/60 focus:bg-accent/60"
              aria-label="Agent name"
              placeholder="Agent name"
              maxLength={120}
            />
            {errors.name && <p className="px-0.5 text-xs text-danger">{errors.name}</p>}
            <input
              value={draft.description}
              onChange={(e) => patch({ description: e.target.value })}
              className="-mx-1.5 w-full rounded-md bg-transparent px-1.5 py-0.5 text-sm text-muted-foreground outline-none hover:bg-accent/60 focus:bg-accent/60"
              aria-label="Description"
              placeholder="Add a short description"
              maxLength={2000}
            />
          </div>

          <Tabs value={tab} onValueChange={setTab} className="mt-6">
            <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
              <TabsList>
                {SECTIONS.map((s) => (
                  <TabsTrigger key={s.id} value={s.id}>
                    <s.icon /> {s.label}
                    {sectionErrors(s.fields) && <span className="size-1.5 rounded-full bg-danger" aria-label="has errors" />}
                    {s.id === "tools" && draft.tools.length > 0 && (
                      <span className="text-[11px] text-muted-foreground">{draft.tools.length}</span>
                    )}
                    {s.id === "variables" && draft.variables.length > 0 && (
                      <span className="text-[11px] text-muted-foreground">{draft.variables.length}</span>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>
            <div className="mt-6">
              <TabsContent value="behaviour">
                <BehaviourSection draft={draft} patch={patch} errors={errors} />
              </TabsContent>
              <TabsContent value="voice">
                <VoiceSection draft={draft} patch={patch} errors={errors} catalog={catalog.data} />
              </TabsContent>
              <TabsContent value="conversation">
                <ConversationSection draft={draft} patch={patch} errors={errors} />
              </TabsContent>
              <TabsContent value="variables">
                <VariablesSection draft={draft} patch={patch} errors={errors} />
              </TabsContent>
              <TabsContent value="tools">
                <ToolsSection draft={draft} patch={patch} errors={errors} />
              </TabsContent>
            </div>
          </Tabs>
        </div>

        {dirty && (
          <div className="pointer-events-none sticky bottom-4 z-20 flex justify-center px-4">
            <div className="pointer-events-auto flex animate-fade-in items-center gap-3 rounded-xl border bg-surface/95 py-2 pl-4 pr-2 shadow-lg backdrop-blur">
              <span className="text-sm">Unsaved changes</span>
              <Button size="sm" variant="ghost" onClick={() => { setDraft(saved); setErrors({}); }} disabled={saving}>
                Discard
              </Button>
              <Button size="sm" variant="primary" onClick={save} loading={saving}>
                Save <span className="hidden text-[11px] opacity-70 sm:inline">⌘S</span>
              </Button>
            </div>
          </div>
        )}
      </div>

      <aside className="sticky top-0 hidden h-dvh w-[380px] shrink-0 border-l bg-surface xl:block">{testCall}</aside>

      <Confirm
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${agent.name}?`}
        description="Any phone numbers routed to it stop being answered. Call history is kept."
        onConfirm={async () => {
          try {
            await api.deleteAgent(agent.id);
            void qc.invalidateQueries({ queryKey: keys.agents });
            void qc.invalidateQueries({ queryKey: keys.trunks });
            toast.success(`Deleted ${agent.name}`);
            router.replace("/agents");
          } catch (err) {
            toast.error(errorMessage(err));
          }
        }}
      />
    </div>
  );
}

export default function AgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const agent = useAgent(id);

  if (agent.isError) {
    const notFound = agent.error instanceof ApiError && agent.error.status === 404;
    return (
      <div className="mx-auto max-w-4xl px-4 py-10 md:px-8">
        <Card>
          <ErrorState
            message={notFound ? "This agent doesn't exist or was deleted." : errorMessage(agent.error)}
            onRetry={notFound ? undefined : () => agent.refetch()}
          />
        </Card>
      </div>
    );
  }
  if (!agent.data) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-6 md:px-8">
        <Skeleton className="h-6 w-24" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="mt-6 h-8 w-[480px] max-w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  // Keyed by id so switching agents (e.g. after Duplicate) starts a fresh draft.
  return <Editor key={agent.data.id} agent={agent.data} />;
}
