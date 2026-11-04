"use client";

import { AlertTriangle, Braces, Check, Plus, Trash2 } from "lucide-react";
import { useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Field, Input, inputClass, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { AgentIn, Catalog, Variable } from "@/lib/types";
import { useCatalog } from "@/lib/queries";
import { cn, placeholders } from "@/lib/utils";

export type Errors = Record<string, string>;
export type Patch = (changes: Partial<AgentIn>) => void;

export interface SectionProps {
  draft: AgentIn;
  patch: Patch;
  errors: Errors;
}

/** Values every call provides, whatever the agent defines; undefined until the catalog loads. */
function useBuiltinVariables() {
  return useCatalog().data?.builtin_variables;
}

export function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function VariableInserter({ variables, onInsert }: { variables: Variable[]; onInsert: (name: string) => void }) {
  const builtins = useBuiltinVariables();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="ghost">
          <Braces /> Insert variable
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-64">
        {variables.length > 0 && (
          <>
            <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground">This agent</div>
            {variables.map((v) => (
              <DropdownMenuItem key={v.name} onSelect={() => onInsert(v.name)}>
                <span className="font-mono text-xs">{v.name}</span>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
          </>
        )}
        <div className="px-2 py-1 text-[11px] font-medium text-muted-foreground">Every call</div>
        {(builtins ?? []).map((v) => (
          <DropdownMenuItem key={v.name} onSelect={() => onInsert(v.name)} className="flex-col items-start gap-0">
            <span className="font-mono text-xs">{v.name}</span>
            <span className="text-[11px] text-muted-foreground">{v.description}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UnknownPlaceholders({ texts, variables }: { texts: string[]; variables: Variable[] }) {
  const builtins = useBuiltinVariables();
  const known = new Set([...variables.map((v) => v.name), ...(builtins ?? []).map((v) => v.name)]);
  // Until the catalog loads, every built-in would look undefined.
  if (!builtins) return null;
  const unknown = [...new Set(texts.flatMap(placeholders))].filter((p) => !known.has(p));
  if (!unknown.length) return null;
  return (
    <p className="flex items-start gap-1.5 text-xs text-warning">
      <AlertTriangle className="mt-px size-3.5 shrink-0" />
      <span>
        {unknown.map((u) => `{{${u}}}`).join(", ")} {unknown.length === 1 ? "isn't" : "aren't"} defined, so{" "}
        {unknown.length === 1 ? "it" : "they"} will be empty. Add {unknown.length === 1 ? "it" : "them"} under Variables.
      </span>
    </p>
  );
}

export function BehaviourSection({ draft, patch, errors }: SectionProps) {
  const prompt = useRef<HTMLTextAreaElement>(null);

  function insert(name: string) {
    const el = prompt.current;
    const token = `{{${name}}}`;
    if (!el) return patch({ prompt: draft.prompt + token });
    const start = el.selectionStart ?? draft.prompt.length;
    const end = el.selectionEnd ?? start;
    const next = draft.prompt.slice(0, start) + token + draft.prompt.slice(end);
    patch({ prompt: next });
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  }

  return (
    <div className="space-y-8">
      <Section title="Prompt" description="Who the agent is, what it should achieve, and how it should speak.">
        <div className="overflow-hidden rounded-lg border border-input bg-surface shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20">
          <div className="flex items-center justify-between border-b bg-surface-2/60 px-2 py-1">
            <VariableInserter variables={draft.variables} onInsert={insert} />
            <span className="pr-1 text-[11px] tabular-nums text-muted-foreground">
              {draft.prompt.length.toLocaleString()} / 50,000
            </span>
          </div>
          <textarea
            ref={prompt}
            value={draft.prompt}
            onChange={(e) => patch({ prompt: e.target.value })}
            placeholder={
              "You are Maya, a friendly receptionist for Acme Dental.\n\n# Goal\nBook, move or cancel appointments.\n\n# Style\nShort sentences. One question at a time. Confirm dates back to the caller."
            }
            className="block min-h-[380px] w-full resize-y bg-transparent px-3.5 py-3 font-mono text-[13px] leading-relaxed outline-none placeholder:text-muted-foreground/60"
            aria-invalid={!!errors.prompt}
            aria-label="Prompt"
            spellCheck
          />
        </div>
        {errors.prompt && <p className="text-xs text-danger">{errors.prompt}</p>}
        <UnknownPlaceholders texts={[draft.prompt, draft.greeting, draft.closing]} variables={draft.variables} />
      </Section>

      <Section title="Opening and closing">
        <Field label="Who speaks first">
          <div className="grid gap-2 sm:grid-cols-2">
            {(
              [
                ["agent", "The agent", "Greets the caller as soon as they connect."],
                ["caller", "The caller", "The agent waits for the caller to speak."],
              ] as const
            ).map(([value, label, hint]) => (
              <button
                key={value}
                type="button"
                onClick={() => patch({ opening: value })}
                aria-pressed={draft.opening === value}
                className={cn(
                  "flex items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:bg-surface-2",
                  draft.opening === value && "border-primary bg-primary-soft/40 ring-1 ring-primary",
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
                    draft.opening === value && "border-primary bg-primary text-primary-foreground",
                  )}
                >
                  {draft.opening === value && <Check className="size-3" />}
                </span>
                <span>
                  <span className="block text-sm font-medium">{label}</span>
                  <span className="block text-xs text-muted-foreground">{hint}</span>
                </span>
              </button>
            ))}
          </div>
        </Field>
        <Field
          label="Greeting"
          htmlFor="greeting"
          error={errors.greeting}
          hint={draft.opening === "agent" ? "The first thing the agent says." : "Used if the caller stays silent."}
        >
          <Textarea
            id="greeting"
            rows={2}
            value={draft.greeting}
            onChange={(e) => patch({ greeting: e.target.value })}
            placeholder="Hi {{customer_name}}, this is Maya from Acme Dental. How can I help?"
          />
        </Field>
        <Field label="Closing" htmlFor="closing" error={errors.closing} hint="Said before the agent hangs up.">
          <Textarea
            id="closing"
            rows={2}
            value={draft.closing}
            onChange={(e) => patch({ closing: e.target.value })}
            placeholder="Thanks for calling. Have a great day!"
          />
        </Field>
      </Section>
    </div>
  );
}

export function VoiceSection({ draft, patch, errors, catalog }: SectionProps & { catalog?: Catalog }) {
  return (
    <div className="space-y-8">
      <Section title="Voice" description="Gemini's native voices. Each has its own character.">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4" role="radiogroup" aria-label="Voice">
          {(catalog?.voices ?? []).map((v) => {
            const selected = draft.voice === v.id;
            return (
              <button
                key={v.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => patch({ voice: v.id })}
                className={cn(
                  "flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left transition-colors hover:bg-surface-2",
                  selected && "border-primary bg-primary-soft/40 ring-1 ring-primary",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{v.id}</span>
                  <span className="block truncate text-xs text-muted-foreground">{v.style}</span>
                </span>
                {selected && <Check className="size-4 shrink-0 text-primary" />}
              </button>
            );
          })}
        </div>
        {errors.voice && <p className="text-xs text-danger">{errors.voice}</p>}
      </Section>

      <Section title="Model and language">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Model" htmlFor="model" error={errors.model}>
            <Select
              id="model"
              value={draft.model}
              onValueChange={(model) => patch({ model })}
              options={(catalog?.models ?? []).map((m) => ({ value: m.id, label: m.name, hint: m.description }))}
            />
          </Field>
          <Field label="Language" htmlFor="language" error={errors.language} hint="Auto-detect follows the caller.">
            <Select
              id="language"
              value={draft.language}
              onValueChange={(language) => patch({ language })}
              options={(catalog?.languages ?? []).map((l) => ({ value: l.id, label: l.name }))}
            />
          </Field>
        </div>
        <Field
          label="Creativity"
          htmlFor="temperature"
          error={errors.temperature}
          aside={<span className="font-mono text-xs tabular-nums text-muted-foreground">{draft.temperature.toFixed(1)}</span>}
          hint="Lower is more consistent and literal; higher is more varied. 0.6–0.8 suits most agents."
        >
          <input
            id="temperature"
            type="range"
            min={0}
            max={2}
            step={0.1}
            value={draft.temperature}
            onChange={(e) => patch({ temperature: Number(e.target.value) })}
            className="w-full accent-[var(--color-primary)]"
          />
        </Field>
      </Section>
    </div>
  );
}

function ToggleRow({
  title,
  description,
  checked,
  onChange,
  badge,
}: {
  title: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  badge?: string;
}) {
  const id = title.toLowerCase().replace(/\W+/g, "-");
  return (
    <div className="flex items-start justify-between gap-4 px-4 py-3">
      <label htmlFor={id} className="min-w-0 cursor-pointer">
        <span className="flex items-center gap-2 text-sm font-medium">
          {title}
          {badge && <Badge tone="outline">{badge}</Badge>}
        </span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
      </label>
      <Switch id={id} checked={checked} onCheckedChange={onChange} className="mt-0.5" />
    </div>
  );
}

function SecondsField({
  label,
  hint,
  value,
  min,
  max,
  onChange,
  error,
}: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
  error?: string;
}) {
  const id = label.toLowerCase().replace(/\W+/g, "-");
  const minutes = value >= 60 ? `${Math.floor(value / 60)}m${value % 60 ? ` ${value % 60}s` : ""}` : null;
  return (
    <Field label={label} htmlFor={id} hint={hint} error={error}>
      <div className="relative">
        <Input
          id={id}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          value={Number.isFinite(value) ? value : ""}
          onChange={(e) => onChange(e.target.valueAsNumber)}
          className="pr-20 tabular-nums"
          aria-invalid={!!error}
        />
        <span className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center text-xs text-muted-foreground">
          seconds{minutes && ` · ${minutes}`}
        </span>
      </div>
    </Field>
  );
}

export function ConversationSection({ draft, patch, errors }: SectionProps) {
  return (
    <div className="space-y-8">
      <Section title="Turn-taking" description="How the agent shares the conversation with the caller.">
        <div className="divide-y rounded-lg border bg-surface">
          <ToggleRow
            title="Allow interruptions"
            description="The agent stops talking when the caller speaks over it."
            checked={draft.allow_interruptions}
            onChange={(v) => patch({ allow_interruptions: v })}
          />
          <ToggleRow
            title="Greeting can be interrupted"
            description="Off makes sure the whole greeting is heard, e.g. for a required disclosure."
            checked={draft.greeting_interruptible}
            onChange={(v) => patch({ greeting_interruptible: v })}
          />
          <ToggleRow
            title="Ignore backchannels"
            description={'Short sounds like "mm-hm" or "okay" don\'t count as interruptions.'}
            checked={draft.backchannel_gate}
            onChange={(v) => patch({ backchannel_gate: v })}
          />
          <ToggleRow
            title="Check in on silence"
            description="If the caller goes quiet, the agent prompts them instead of waiting forever."
            checked={draft.silence_monitor}
            onChange={(v) => patch({ silence_monitor: v })}
          />
        </div>
      </Section>

      <Section title="Phone calls">
        <div className="divide-y rounded-lg border bg-surface">
          <ToggleRow
            title="Background ambience"
            description="Adds soft office noise so pauses don't sound like a dropped line."
            checked={draft.background_noise}
            onChange={(v) => patch({ background_noise: v })}
          />
          <ToggleRow
            title="Voicemail detection"
            description="Detects answering machines on calls the agent places, and ends those calls."
            badge="Outbound"
            checked={draft.voicemail_detection}
            onChange={(v) => patch({ voicemail_detection: v })}
          />
        </div>
      </Section>

      <Section title="Limits">
        <div className="grid gap-4 sm:grid-cols-2">
          <SecondsField
            label="Maximum call length"
            hint="The agent wraps up and hangs up at this point. 30–7200."
            value={draft.max_call_duration_seconds}
            min={30}
            max={7200}
            onChange={(v) => patch({ max_call_duration_seconds: v })}
            error={errors.max_call_duration_seconds}
          />
          <SecondsField
            label="Hang up if nobody responds"
            hint="Ends the call when the caller says nothing at all for this long. 5–300."
            value={draft.engagement_timeout_seconds}
            min={5}
            max={300}
            onChange={(v) => patch({ engagement_timeout_seconds: v })}
            error={errors.engagement_timeout_seconds}
          />
        </div>
      </Section>
    </div>
  );
}

export function VariablesSection({ draft, patch, errors }: SectionProps) {
  const builtins = useBuiltinVariables();
  const set = (i: number, changes: Partial<Variable>) =>
    patch({ variables: draft.variables.map((v, j) => (j === i ? { ...v, ...changes } : v)) });

  return (
    <Section
      title="Variables"
      description="Values filled in per call wherever {{name}} appears in the prompt, greeting or closing. Set them when placing a call; the default is used otherwise."
    >
      {draft.variables.length > 0 && (
        <div className="space-y-2">
          <div className="hidden grid-cols-[1fr_1fr_1.4fr_2rem] gap-2 px-0.5 text-xs font-medium text-muted-foreground sm:grid">
            <span>Name</span>
            <span>Default</span>
            <span>Description</span>
            <span />
          </div>
          {draft.variables.map((v, i) => (
            <div key={i} className="grid gap-2 rounded-lg border p-2 sm:grid-cols-[1fr_1fr_1.4fr_2rem] sm:border-0 sm:p-0">
              <div>
                <input
                  className={cn(inputClass, "h-8 font-mono text-[13px]")}
                  placeholder="customer_name"
                  value={v.name}
                  onChange={(e) => set(i, { name: e.target.value.replace(/[^a-zA-Z0-9_]/g, "_") })}
                  aria-label="Variable name"
                  aria-invalid={!!errors[`variables.${i}.name`]}
                />
                {errors[`variables.${i}.name`] && (
                  <p className="mt-1 text-xs text-danger">{errors[`variables.${i}.name`]}</p>
                )}
              </div>
              <Input placeholder="there" value={v.default} onChange={(e) => set(i, { default: e.target.value })} aria-label="Default value" />
              <Input
                placeholder="The customer's first name"
                value={v.description}
                onChange={(e) => set(i, { description: e.target.value })}
                aria-label="Description"
              />
              <Button
                size="icon"
                variant="ghost"
                onClick={() => patch({ variables: draft.variables.filter((_, j) => j !== i) })}
                aria-label={`Remove ${v.name || "variable"}`}
              >
                <Trash2 />
              </Button>
            </div>
          ))}
        </div>
      )}
      {errors.variables && <p className="text-xs text-danger">{errors.variables}</p>}
      <Button
        size="sm"
        onClick={() => patch({ variables: [...draft.variables, { name: "", default: "", description: "" }] })}
      >
        <Plus /> Add variable
      </Button>
      <div className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
        Always available:{" "}
        {(builtins ?? []).map((b, i, all) => (
          <span key={b.name} title={b.description}>
            <code className="font-mono text-foreground/80">{`{{${b.name}}}`}</code>
            {i < all.length - 1 ? ", " : ""}
          </span>
        ))}
      </div>
    </Section>
  );
}
