"use client";

import { Pencil, Plus, Trash2, Wrench } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { emptyTool } from "@/lib/agent-defaults";
import type { Tool, ToolParameter } from "@/lib/types";
import { Section, type SectionProps } from "./sections";

const IDENT = /^[a-zA-Z_][a-zA-Z0-9_]{0,63}$/;

function validate(tool: Tool, others: Tool[]): Record<string, string> {
  const e: Record<string, string> = {};
  if (!IDENT.test(tool.name)) e.name = "Use letters, numbers and _, e.g. check_order_status";
  else if (others.some((t) => t.name === tool.name)) e.name = "Another tool already has this name";
  if (!tool.description.trim()) e.description = "Describe when the agent should use it";
  try {
    const u = new URL(tool.url);
    if (!/^https?:$/.test(u.protocol)) throw new Error();
  } catch {
    e.url = "Enter a full http(s) URL";
  }
  const names = new Set<string>();
  tool.parameters.forEach((p, i) => {
    if (!IDENT.test(p.name)) e[`parameters.${i}.name`] = "Letters, numbers and _";
    else if (names.has(p.name)) e[`parameters.${i}.name`] = "Duplicate name";
    names.add(p.name);
  });
  return e;
}

function ToolDialog({
  tool: initial,
  others,
  open,
  onOpenChange,
  onSave,
}: {
  tool: Tool;
  others: Tool[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSave: (t: Tool) => void;
}) {
  const [tool, setTool] = useState<Tool>(initial);
  const [headers, setHeaders] = useState(() => Object.entries(initial.headers).map(([k, v]) => ({ k, v })));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = (c: Partial<Tool>) => setTool((t) => ({ ...t, ...c }));
  const setParam = (i: number, c: Partial<ToolParameter>) =>
    set({ parameters: tool.parameters.map((p, j) => (j === i ? { ...p, ...c } : p)) });

  function save() {
    const result = { ...tool, headers: Object.fromEntries(headers.filter((h) => h.k.trim()).map((h) => [h.k.trim(), h.v])) };
    const e = validate(result, others);
    setErrors(e);
    if (Object.keys(e).length === 0) {
      onSave(result);
      onOpenChange(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={initial.name ? `Edit ${initial.name}` : "Add a tool"}
        description="When the agent decides to use this tool, the studio calls your URL and reads the JSON response back to the agent."
        className="max-w-2xl"
        footer={
          <>
            <Button onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button variant="primary" onClick={save}>
              Save tool
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field label="Name" htmlFor="tool-name" error={errors.name}>
              <Input
                id="tool-name"
                className="font-mono text-[13px]"
                placeholder="check_order_status"
                value={tool.name}
                onChange={(e) => set({ name: e.target.value.replace(/[^a-zA-Z0-9_]/g, "_") })}
                aria-invalid={!!errors.name}
              />
            </Field>
            <Field label="Timeout" htmlFor="tool-timeout" hint="1–30 s">
              <Input
                id="tool-timeout"
                type="number"
                min={1}
                max={30}
                value={tool.timeout_seconds}
                onChange={(e) => set({ timeout_seconds: Math.min(30, Math.max(1, e.target.valueAsNumber || 10)) })}
              />
            </Field>
          </div>
          <Field
            label="When to use it"
            htmlFor="tool-desc"
            error={errors.description}
            hint="The agent reads this to decide when to call the tool. Be specific."
          >
            <Textarea
              id="tool-desc"
              rows={2}
              placeholder="Look up the delivery status of an order when the caller gives an order number."
              value={tool.description}
              onChange={(e) => set({ description: e.target.value })}
              aria-invalid={!!errors.description}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-[7rem_1fr]">
            <Field label="Method" htmlFor="tool-method">
              <Select
                id="tool-method"
                value={tool.method}
                onValueChange={(m) => set({ method: m as Tool["method"] })}
                options={[
                  { value: "POST", label: "POST" },
                  { value: "GET", label: "GET" },
                ]}
              />
            </Field>
            <Field
              label="URL"
              htmlFor="tool-url"
              error={errors.url}
              hint={
                tool.method === "POST"
                  ? 'Receives JSON: { "arguments": {...}, "call": { "call_id", "direction", "from_number", "to_number", "variables" } }'
                  : "Arguments are sent as query parameters."
              }
            >
              <Input
                id="tool-url"
                className="font-mono text-[13px]"
                placeholder="https://api.example.com/orders/status"
                value={tool.url}
                onChange={(e) => set({ url: e.target.value })}
                aria-invalid={!!errors.url}
              />
            </Field>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium">Parameters</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  set({
                    parameters: [
                      ...tool.parameters,
                      { name: "", type: "string", description: "", required: true, enum: [] },
                    ],
                  })
                }
              >
                <Plus /> Add parameter
              </Button>
            </div>
            {tool.parameters.length === 0 ? (
              <p className="rounded-lg border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
                No parameters: the agent calls it without any arguments.
              </p>
            ) : (
              <div className="space-y-2">
                {tool.parameters.map((p, i) => (
                  <div key={i} className="space-y-2 rounded-lg border p-2.5">
                    <div className="grid gap-2 sm:grid-cols-[1fr_8rem_auto_2rem] sm:items-center">
                      <div>
                        <Input
                          className="font-mono text-[13px]"
                          placeholder="order_number"
                          value={p.name}
                          onChange={(e) => setParam(i, { name: e.target.value.replace(/[^a-zA-Z0-9_]/g, "_") })}
                          aria-label="Parameter name"
                          aria-invalid={!!errors[`parameters.${i}.name`]}
                        />
                        {errors[`parameters.${i}.name`] && (
                          <p className="mt-1 text-xs text-danger">{errors[`parameters.${i}.name`]}</p>
                        )}
                      </div>
                      <Select
                        value={p.type}
                        onValueChange={(type) => setParam(i, { type: type as ToolParameter["type"] })}
                        options={["string", "number", "integer", "boolean"].map((t) => ({ value: t, label: t }))}
                      />
                      <label className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Switch checked={p.required} onCheckedChange={(required) => setParam(i, { required })} />
                        Required
                      </label>
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => set({ parameters: tool.parameters.filter((_, j) => j !== i) })}
                        aria-label="Remove parameter"
                      >
                        <Trash2 />
                      </Button>
                    </div>
                    <Input
                      placeholder="What this value is, e.g. The 8-digit order number"
                      value={p.description}
                      onChange={(e) => setParam(i, { description: e.target.value })}
                      aria-label="Parameter description"
                    />
                    {p.type === "string" && (
                      <Input
                        placeholder="Allowed values (optional, comma-separated)"
                        value={p.enum.join(", ")}
                        onChange={(e) =>
                          setParam(i, {
                            enum: e.target.value
                              .split(",")
                              .map((s) => s.trim())
                              .filter(Boolean),
                          })
                        }
                        aria-label="Allowed values"
                      />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium">Headers</span>
              <Button size="sm" variant="ghost" onClick={() => setHeaders([...headers, { k: "", v: "" }])}>
                <Plus /> Add header
              </Button>
            </div>
            {headers.map((h, i) => (
              <div key={i} className="grid grid-cols-[1fr_1.5fr_2rem] gap-2">
                <Input
                  placeholder="Authorization"
                  value={h.k}
                  onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, k: e.target.value } : x)))}
                  aria-label="Header name"
                />
                <Input
                  placeholder="Bearer …"
                  value={h.v}
                  onChange={(e) => setHeaders(headers.map((x, j) => (j === i ? { ...x, v: e.target.value } : x)))}
                  aria-label="Header value"
                />
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => setHeaders(headers.filter((_, j) => j !== i))}
                  aria-label="Remove header"
                >
                  <Trash2 />
                </Button>
              </div>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ToolsSection({ draft, patch, errors }: SectionProps) {
  const [editing, setEditing] = useState<{ index: number | null; tool: Tool } | null>(null);
  const toolErrors = Object.entries(errors).filter(([k]) => k.startsWith("tools"));

  return (
    <Section
      title="Tools"
      description="Let the agent look things up or take actions mid-call by calling your APIs."
    >
      {draft.tools.length === 0 ? (
        <div className="flex flex-col items-center rounded-lg border border-dashed px-6 py-10 text-center">
          <Wrench className="size-5 text-muted-foreground" />
          <p className="mt-2 text-sm font-medium">No tools yet</p>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            For example: check an order, book an appointment or create a support ticket.
          </p>
        </div>
      ) : (
        <ul className="divide-y rounded-lg border bg-surface">
          {draft.tools.map((t, i) => (
            <li key={`${t.name}-${i}`} className="flex items-start gap-3 px-4 py-3">
              <Wrench className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[13px] font-medium">{t.name}</span>
                  <Badge tone="outline">{t.method}</Badge>
                  {t.parameters.length > 0 && (
                    <span className="text-xs text-muted-foreground">
                      {t.parameters.map((p) => p.name).join(", ")}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{t.description}</p>
                <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground/80">{t.url}</p>
              </div>
              <Button size="icon-sm" variant="ghost" onClick={() => setEditing({ index: i, tool: t })} aria-label={`Edit ${t.name}`}>
                <Pencil />
              </Button>
              <Button
                size="icon-sm"
                variant="ghost"
                onClick={() => patch({ tools: draft.tools.filter((_, j) => j !== i) })}
                aria-label={`Remove ${t.name}`}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {toolErrors.map(([k, v]) => (
        <p key={k} className="text-xs text-danger">
          {k.replace(/^tools\.(\d+)\./, (_, n) => `${draft.tools[Number(n)]?.name ?? "Tool"}: `)}
          {v}
        </p>
      ))}
      <Button size="sm" onClick={() => setEditing({ index: null, tool: emptyTool() })}>
        <Plus /> Add tool
      </Button>
      {editing && (
        <ToolDialog
          key={editing.index ?? "new"}
          tool={editing.tool}
          others={draft.tools.filter((_, i) => i !== editing.index)}
          open
          onOpenChange={(o) => !o && setEditing(null)}
          onSave={(tool) =>
            patch({
              tools:
                editing.index === null
                  ? [...draft.tools, tool]
                  : draft.tools.map((t, i) => (i === editing.index ? tool : t)),
            })
          }
        />
      )}
    </Section>
  );
}
