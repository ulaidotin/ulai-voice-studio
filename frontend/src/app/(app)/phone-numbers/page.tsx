"use client";

import { useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, PhoneIncoming, PhoneOutgoing, Plus, Trash2, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { Page, PageHeader } from "@/components/shell/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Confirm } from "@/components/ui/confirm";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Empty, ErrorState } from "@/components/ui/empty";
import { Field, Input, inputClass } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError, errorMessage } from "@/lib/api";
import { keys, useAgents, useTrunks } from "@/lib/queries";
import type { Transport, Trunk, TrunkDirection } from "@/lib/types";
import { cn, formatPhone } from "@/lib/utils";

/** A list of values typed one at a time; Enter, comma or paste adds them. */
function ChipsInput({
  values,
  onChange,
  placeholder,
  id,
  mono,
  invalid,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  id?: string;
  mono?: boolean;
  invalid?: boolean;
}) {
  const [text, setText] = useState("");
  const add = (raw: string) => {
    const items = raw
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (items.length) onChange([...new Set([...values, ...items])]);
    setText("");
  };
  return (
    <div
      className={cn(inputClass, "flex min-h-8 flex-wrap items-center gap-1 px-1.5 py-1", invalid && "border-danger")}
      onClick={(e) => (e.currentTarget.querySelector("input") as HTMLInputElement | null)?.focus()}
    >
      {values.map((v) => (
        <span key={v} className={cn("inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs", mono && "font-mono")}>
          {v}
          <button
            type="button"
            onClick={() => onChange(values.filter((x) => x !== v))}
            className="text-muted-foreground hover:text-foreground"
            aria-label={`Remove ${v}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(text);
          } else if (e.key === "Backspace" && !text && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={() => text && add(text)}
        onPaste={(e) => {
          const pasted = e.clipboardData.getData("text");
          if (/[,\s]/.test(pasted.trim())) {
            e.preventDefault();
            add(pasted);
          }
        }}
        placeholder={values.length ? "" : placeholder}
        className={cn("h-6 min-w-32 flex-1 bg-transparent px-1 text-sm outline-none", mono && "font-mono")}
      />
    </div>
  );
}

function fieldErrors(err: unknown): Record<string, string> | null {
  if (err instanceof ApiError && err.fields.length) {
    return Object.fromEntries(err.fields.map((f) => [String(f.path[0] ?? "form"), f.message]));
  }
  return null;
}

function InboundDialog({ trunk, onClose }: { trunk: Trunk | null; onClose: () => void }) {
  const qc = useQueryClient();
  const agents = useAgents();
  const [name, setName] = useState(trunk?.name ?? "");
  const [numbers, setNumbers] = useState<string[]>(trunk?.numbers ?? []);
  const [allowed, setAllowed] = useState<string[]>(trunk?.allowed_addresses ?? []);
  const [agentId, setAgentId] = useState(trunk?.agent?.id ?? "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      if (trunk) {
        await api.updateTrunk(trunk.id, { name, numbers, allowed_addresses: allowed, agent_id: agentId || null });
      } else {
        await api.createInbound({ name, numbers, allowed_addresses: allowed, agent_id: agentId || null });
      }
      await qc.invalidateQueries({ queryKey: keys.trunks });
      void qc.invalidateQueries({ queryKey: keys.agents });
      toast.success(trunk ? "Trunk updated" : "Inbound trunk added");
      onClose();
    } catch (err) {
      const f = fieldErrors(err);
      if (f) setErrors(f);
      else toast.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <DialogContent
      title={trunk ? `Edit ${trunk.name}` : "Add inbound trunk"}
      description="Calls to these numbers from your SIP provider are answered by the agent you choose."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" form="inbound-form" loading={busy} disabled={!name || !numbers.length}>
            {trunk ? "Save" : "Add trunk"}
          </Button>
        </>
      }
    >
      <form id="inbound-form" onSubmit={save} className="space-y-4">
        <Field label="Name" htmlFor="in-name" error={errors.name}>
          <Input id="in-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Support line" />
        </Field>
        <Field
          label="Phone numbers"
          htmlFor="in-numbers"
          error={errors.numbers}
          hint="With country code. Press Enter after each one."
        >
          <ChipsInput id="in-numbers" values={numbers} onChange={setNumbers} placeholder="+14155550123" mono invalid={!!errors.numbers} />
        </Field>
        <Field
          label="Answered by"
          htmlFor="in-agent"
          error={errors.agent_id}
          hint="Leave unassigned to stop answering calls on this trunk."
        >
          <Select
            id="in-agent"
            value={agentId}
            onValueChange={setAgentId}
            options={[{ value: "", label: "Unassigned" }, ...(agents.data ?? []).map((a) => ({ value: a.id, label: a.name }))]}
          />
        </Field>
        <Field
          label="Allowed source addresses"
          htmlFor="in-allowed"
          error={errors.allowed_addresses}
          hint="Optional. Your provider's signalling IPs or CIDR ranges; leave empty to accept any."
        >
          <ChipsInput id="in-allowed" values={allowed} onChange={setAllowed} placeholder="54.172.60.0/30" mono />
        </Field>
        {errors.form && <p className="text-sm text-danger">{errors.form}</p>}
      </form>
    </DialogContent>
  );
}

function OutboundDialog({ trunk, onClose }: { trunk: Trunk | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(trunk?.name ?? "");
  const [address, setAddress] = useState(trunk?.address ?? "");
  const [transport, setTransport] = useState<Transport>(trunk?.transport ?? "auto");
  const [username, setUsername] = useState(trunk?.username ?? "");
  const [password, setPassword] = useState("");
  const [numbers, setNumbers] = useState<string[]>(trunk?.numbers ?? []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      if (trunk) {
        await api.updateTrunk(trunk.id, {
          name,
          address,
          transport,
          username,
          numbers,
          ...(password ? { password } : {}),
        });
      } else {
        await api.createOutbound({ name, address, transport, username, password, numbers });
      }
      await qc.invalidateQueries({ queryKey: keys.trunks });
      toast.success(trunk ? "Trunk updated" : "Outbound trunk added");
      onClose();
    } catch (err) {
      const f = fieldErrors(err);
      if (f) setErrors(f);
      else toast.error(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <DialogContent
      title={trunk ? `Edit ${trunk.name}` : "Add outbound trunk"}
      description="Your SIP provider's termination details, used when an agent places a call."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            type="submit"
            form="outbound-form"
            loading={busy}
            disabled={!name || !address || !numbers.length}
          >
            {trunk ? "Save" : "Add trunk"}
          </Button>
        </>
      }
    >
      <form id="outbound-form" onSubmit={save} className="space-y-4" autoComplete="off">
        <Field label="Name" htmlFor="out-name" error={errors.name}>
          <Input id="out-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Twilio US" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
          <Field label="SIP address" htmlFor="out-address" error={errors.address} hint="Host or host:port from your provider.">
            <Input
              id="out-address"
              className="font-mono text-[13px]"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="example.pstn.twilio.com"
            />
          </Field>
          <Field label="Transport" htmlFor="out-transport" error={errors.transport}>
            <Select
              id="out-transport"
              value={transport}
              onValueChange={(v) => setTransport(v as Transport)}
              options={[
                { value: "auto", label: "Auto" },
                { value: "udp", label: "UDP" },
                { value: "tcp", label: "TCP" },
                { value: "tls", label: "TLS" },
              ]}
            />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Username" htmlFor="out-user" error={errors.username}>
            <Input id="out-user" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
          </Field>
          <Field
            label="Password"
            htmlFor="out-pass"
            error={errors.password}
            hint={trunk ? "Leave blank to keep the current one." : "Stored by Ulai, never shown again."}
          >
            <Input
              id="out-pass"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              placeholder={trunk ? "••••••••" : ""}
            />
          </Field>
        </div>
        <Field
          label="Caller ID numbers"
          htmlFor="out-numbers"
          error={errors.numbers}
          hint="Numbers you own at this provider; calls can be placed from any of them."
        >
          <ChipsInput id="out-numbers" values={numbers} onChange={setNumbers} placeholder="+14155550123" mono invalid={!!errors.numbers} />
        </Field>
        {errors.form && <p className="text-sm text-danger">{errors.form}</p>}
      </form>
    </DialogContent>
  );
}

function TrunkRow({ trunk, onEdit }: { trunk: Trunk; onEdit: () => void }) {
  const qc = useQueryClient();
  const [toggling, setToggling] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function toggle(enabled: boolean) {
    setToggling(true);
    try {
      await api.setTrunkEnabled(trunk.id, enabled);
      await qc.invalidateQueries({ queryKey: keys.trunks });
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setToggling(false);
    }
  }

  return (
    <li className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3", !trunk.enabled && "opacity-60")}>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{trunk.name}</span>
          {!trunk.enabled && <Badge>Disabled</Badge>}
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {trunk.numbers.map((n) => (
            <span key={n} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">
              {formatPhone(n)}
            </span>
          ))}
        </div>
        {trunk.direction === "outbound" && (
          <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
            {trunk.address} · {trunk.transport.toUpperCase()}
            {trunk.username && ` · ${trunk.username}`}
          </div>
        )}
      </div>
      {trunk.direction === "inbound" && (
        <div className="w-full text-sm sm:w-48">
          {trunk.agent ? (
            <span className="text-foreground/90">→ {trunk.agent.name}</span>
          ) : (
            <span className="text-warning">Not answered: no agent</span>
          )}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Switch
          checked={trunk.enabled}
          onCheckedChange={toggle}
          disabled={toggling}
          aria-label={trunk.enabled ? `Disable ${trunk.name}` : `Enable ${trunk.name}`}
        />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="icon-sm" variant="ghost" aria-label="Trunk actions">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={onEdit}>
              <Pencil /> Edit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem danger onSelect={() => setConfirmDelete(true)}>
              <Trash2 /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <Confirm
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${trunk.name}?`}
        description={
          trunk.direction === "inbound"
            ? "Calls to its numbers will no longer reach your agents. This removes it from Ulai too."
            : "Agents can no longer place calls through it. This removes it from Ulai too."
        }
        onConfirm={async () => {
          try {
            await api.deleteTrunk(trunk.id);
            await qc.invalidateQueries({ queryKey: keys.trunks });
            void qc.invalidateQueries({ queryKey: keys.agents });
            toast.success(`Deleted ${trunk.name}`);
          } catch (err) {
            toast.error(errorMessage(err));
          }
        }}
      />
    </li>
  );
}

const COPY: Record<TrunkDirection, { title: string; blurb: string; empty: string; icon: typeof PhoneIncoming }> = {
  inbound: {
    title: "Inbound",
    blurb: "Numbers people call. Each inbound trunk routes its numbers to one agent.",
    empty: "Add the numbers your SIP provider forwards to Ulai, and pick the agent that answers them.",
    icon: PhoneIncoming,
  },
  outbound: {
    title: "Outbound",
    blurb: "Your SIP provider's connection for calls the agents place.",
    empty: "Add your provider's SIP address and credentials so agents can call phone numbers.",
    icon: PhoneOutgoing,
  },
};

function PhoneNumbersView() {
  const trunks = useTrunks();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const tab: TrunkDirection = params.get("tab") === "outbound" ? "outbound" : "inbound";
  const [editing, setEditing] = useState<{ direction: TrunkDirection; trunk: Trunk | null } | null>(null);

  const list = (direction: TrunkDirection) => (trunks.data ?? []).filter((t) => t.direction === direction);

  return (
    <Page>
      <PageHeader
        title="Phone numbers"
        description="Connect your SIP provider to answer and place phone calls."
        actions={
          <Button variant="primary" onClick={() => setEditing({ direction: tab, trunk: null })}>
            <Plus /> Add {tab} trunk
          </Button>
        }
      />
      <Tabs value={tab} onValueChange={(v) => router.replace(`${pathname}?tab=${v}`, { scroll: false })}>
        <TabsList>
          {(["inbound", "outbound"] as const).map((d) => {
            const Icon = COPY[d].icon;
            return (
              <TabsTrigger key={d} value={d}>
                <Icon /> {COPY[d].title}
                {trunks.data && <span className="text-[11px] text-muted-foreground">{list(d).length}</span>}
              </TabsTrigger>
            );
          })}
        </TabsList>
        {(["inbound", "outbound"] as const).map((d) => (
          <TabsContent key={d} value={d} className="mt-4 space-y-3">
            <p className="text-sm text-muted-foreground">{COPY[d].blurb}</p>
            <Card className="overflow-hidden">
              {trunks.isError ? (
                <ErrorState message={errorMessage(trunks.error)} onRetry={() => trunks.refetch()} />
              ) : trunks.isLoading ? (
                <div className="space-y-3 p-4">
                  <Skeleton className="h-5 w-1/3" />
                  <Skeleton className="h-5 w-1/2" />
                </div>
              ) : list(d).length === 0 ? (
                <Empty
                  icon={COPY[d].icon}
                  title={`No ${d} trunks`}
                  description={COPY[d].empty}
                  action={
                    <Button variant="primary" onClick={() => setEditing({ direction: d, trunk: null })}>
                      <Plus /> Add {d} trunk
                    </Button>
                  }
                />
              ) : (
                <ul className="divide-y">
                  {list(d).map((t) => (
                    <TrunkRow key={t.id} trunk={t} onEdit={() => setEditing({ direction: d, trunk: t })} />
                  ))}
                </ul>
              )}
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        {editing?.direction === "inbound" && (
          <InboundDialog key={editing.trunk?.id ?? "new"} trunk={editing.trunk} onClose={() => setEditing(null)} />
        )}
        {editing?.direction === "outbound" && (
          <OutboundDialog key={editing.trunk?.id ?? "new"} trunk={editing.trunk} onClose={() => setEditing(null)} />
        )}
      </Dialog>
    </Page>
  );
}

export default function PhoneNumbersPage() {
  return (
    <Suspense>
      <PhoneNumbersView />
    </Suspense>
  );
}
