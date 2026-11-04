"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Command } from "cmdk";
import { Bot, Moon, Phone, Plus, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import * as DialogPrimitive from "@radix-ui/react-dialog";

import { api, errorMessage } from "@/lib/api";
import { emptyAgent } from "@/lib/agent-defaults";
import { keys, useAgents } from "@/lib/queries";
import { NAV } from "./nav";
import { useUI } from "./ui-context";

const item =
  "flex cursor-default select-none items-center gap-2.5 rounded-md px-2.5 py-2 text-sm aria-selected:bg-accent [&_svg]:size-4 [&_svg]:text-muted-foreground";
const group =
  "[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground";

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { placeCall } = useUI();
  const { setTheme, resolvedTheme } = useTheme();
  const agents = useAgents();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  function run(fn: () => void) {
    onOpenChange(false);
    fn();
  }

  async function newAgent() {
    try {
      const agent = await api.createAgent(emptyAgent());
      await qc.invalidateQueries({ queryKey: keys.agents });
      router.push(`/agents/${agent.id}`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command menu"
      overlayClassName="fixed inset-0 z-50 bg-black/40 backdrop-blur-[2px]"
      contentClassName="fixed left-1/2 top-[15vh] z-50 w-[calc(100vw-1.5rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl border bg-surface shadow-2xl data-[state=open]:animate-fade-in"
    >
      <DialogPrimitive.Title className="sr-only">Command menu</DialogPrimitive.Title>
      <Command.Input
        placeholder="Search pages, agents and actions…"
        className="h-12 w-full border-b bg-transparent px-4 text-sm outline-none placeholder:text-muted-foreground"
      />
      <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-1.5">
        <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">No results.</Command.Empty>
        <Command.Group heading="Actions" className={group}>
          <Command.Item className={item} onSelect={() => run(newAgent)}>
            <Plus /> New agent
          </Command.Item>
          <Command.Item className={item} onSelect={() => run(() => placeCall())}>
            <Phone /> Place a call
          </Command.Item>
          <Command.Item
            className={item}
            onSelect={() => run(() => setTheme(resolvedTheme === "dark" ? "light" : "dark"))}
          >
            {resolvedTheme === "dark" ? <Sun /> : <Moon />} Switch to {resolvedTheme === "dark" ? "light" : "dark"}{" "}
            theme
          </Command.Item>
        </Command.Group>
        <Command.Group heading="Go to" className={group}>
          {NAV.map((n) => (
            <Command.Item key={n.href} className={item} onSelect={() => run(() => router.push(n.href))}>
              <n.icon /> {n.label}
            </Command.Item>
          ))}
        </Command.Group>
        {!!agents.data?.length && (
          <Command.Group heading="Agents" className={group}>
            {agents.data.map((a) => (
              <Command.Item
                key={a.id}
                value={`agent ${a.name} ${a.id}`}
                className={item}
                onSelect={() => run(() => router.push(`/agents/${a.id}`))}
              >
                <Bot /> {a.name}
              </Command.Item>
            ))}
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  );
}
