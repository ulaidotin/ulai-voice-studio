"use client";

import { useQuery } from "@tanstack/react-query";
import { PhoneOutgoing } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { api, ApiError, errorMessage } from "@/lib/api";
import { keys, useAgents, useTrunks } from "@/lib/queries";
import { formatPhone } from "@/lib/utils";

export function PlaceCallDialog({
  open,
  onOpenChange,
  agentId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && <PlaceCallForm key={agentId ?? "any"} agentId={agentId} onDone={() => onOpenChange(false)} />}
    </Dialog>
  );
}

function PlaceCallForm({ agentId: initialAgent, onDone }: { agentId?: string; onDone: () => void }) {
  const router = useRouter();
  const agents = useAgents();
  const trunks = useTrunks();
  const outbound = (trunks.data ?? []).filter((t) => t.direction === "outbound" && t.enabled);

  const [agentId, setAgentId] = useState(initialAgent ?? "");
  const [trunkId, setTrunkId] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [toNumber, setToNumber] = useState("");
  const [vars, setVars] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const agent = useQuery({ queryKey: keys.agent(agentId), queryFn: () => api.agent(agentId), enabled: !!agentId });
  // Default to the first trunk, and that trunk's first number, until the user picks.
  const trunk = outbound.find((t) => t.id === trunkId) ?? outbound[0];
  const from = fromNumber && trunk?.numbers.includes(fromNumber) ? fromNumber : (trunk?.numbers[0] ?? "");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!agentId || !trunk) return;
    setBusy(true);
    setErrors({});
    try {
      const variables = Object.fromEntries(Object.entries(vars).filter(([, v]) => v.trim() !== ""));
      const call = await api.startOutboundCall({
        agent_id: agentId,
        trunk_id: trunk.id,
        from_number: from || null,
        to_number: toNumber.trim(),
        variables,
      });
      toast.success(`Calling ${formatPhone(call.to_number)}`);
      onDone();
      router.push(`/calls/${call.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.fields.length) {
        setErrors(Object.fromEntries(err.fields.map((f) => [String(f.path[0] ?? "form"), f.message])));
      } else {
        toast.error(errorMessage(err));
      }
      setBusy(false);
    }
  }

  const noTrunks = trunks.isSuccess && outbound.length === 0;

  return (
    <DialogContent
      title="Place a call"
      description="The agent calls the number through one of your outbound SIP trunks."
      footer={
        <>
          <Button onClick={onDone} type="button">
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="place-call"
            loading={busy}
            disabled={!agentId || !trunk || !toNumber.trim()}
          >
            <PhoneOutgoing /> Call
          </Button>
        </>
      }
    >
      {noTrunks ? (
        <div className="rounded-lg border border-dashed p-4 text-sm">
          <p className="font-medium">No outbound trunk yet</p>
          <p className="mt-1 text-muted-foreground">
            Add your SIP provider as an outbound trunk to place phone calls.
          </p>
          <Button asChild size="sm" className="mt-3" onClick={onDone}>
            <Link href="/phone-numbers?tab=outbound">Add an outbound trunk</Link>
          </Button>
        </div>
      ) : (
        <form id="place-call" onSubmit={submit} className="space-y-4">
          <Field label="Agent" htmlFor="pc-agent" error={errors.agent_id}>
            <Select
              id="pc-agent"
              value={agentId}
              onValueChange={setAgentId}
              placeholder={agents.isLoading ? "Loading…" : "Choose an agent"}
              options={(agents.data ?? []).map((a) => ({ value: a.id, label: a.name }))}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Trunk" htmlFor="pc-trunk" error={errors.trunk_id}>
              <Select
                id="pc-trunk"
                value={trunk?.id ?? ""}
                onValueChange={(v) => {
                  setTrunkId(v);
                  setFromNumber("");
                }}
                options={outbound.map((t) => ({ value: t.id, label: t.name }))}
                placeholder="Choose a trunk"
              />
            </Field>
            <Field label="From" htmlFor="pc-from" error={errors.from_number}>
              <Select
                id="pc-from"
                value={from}
                onValueChange={setFromNumber}
                options={(trunk?.numbers ?? []).map((n) => ({ value: n, label: formatPhone(n) }))}
                placeholder="Caller ID"
              />
            </Field>
          </div>
          <Field
            label="To"
            htmlFor="pc-to"
            error={errors.to_number}
            hint="Include the country code, e.g. +14155550123 or +919876543210."
          >
            <Input
              id="pc-to"
              type="tel"
              inputMode="tel"
              autoComplete="off"
              placeholder="+1 415 555 0123"
              value={toNumber}
              onChange={(e) => setToNumber(e.target.value)}
              aria-invalid={!!errors.to_number}
              className="font-mono"
            />
          </Field>
          {!!agent.data?.variables.length && (
            <fieldset className="space-y-3 rounded-lg border p-3">
              <legend className="px-1 text-xs font-medium text-muted-foreground">Variables for this call</legend>
              {agent.data.variables.map((v) => (
                <Field key={v.name} label={<span className="font-mono text-xs">{`{{${v.name}}}`}</span>} hint={v.description}>
                  <Input
                    value={vars[v.name] ?? ""}
                    placeholder={v.default ? `Default: ${v.default}` : undefined}
                    onChange={(e) => setVars({ ...vars, [v.name]: e.target.value })}
                  />
                </Field>
              ))}
            </fieldset>
          )}
          {errors.form && <p className="text-sm text-danger">{errors.form}</p>}
        </form>
      )}
    </DialogContent>
  );
}
