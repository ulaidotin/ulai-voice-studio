"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export interface Option {
  value: string;
  label: React.ReactNode;
  hint?: React.ReactNode;
}

// Radix Select can't use "" as an item value, so empty selections travel as this sentinel.
const EMPTY = "__empty__";

export function Select({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  className,
  id,
  disabled,
  "aria-invalid": invalid,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: Option[];
  placeholder?: string;
  className?: string;
  id?: string;
  disabled?: boolean;
  "aria-invalid"?: boolean;
}) {
  return (
    <SelectPrimitive.Root
      value={value === "" ? (options.some((o) => o.value === "") ? EMPTY : undefined) : value}
      onValueChange={(v) => onValueChange(v === EMPTY ? "" : v)}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        id={id}
        aria-invalid={invalid}
        className={cn(
          "flex h-8 w-full items-center justify-between gap-2 rounded-md border border-input bg-surface px-2.5 text-left text-sm shadow-xs focus-visible:border-ring focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/20 disabled:opacity-60 aria-invalid:border-danger data-[placeholder]:text-muted-foreground",
          className,
        )}
      >
        <span className="truncate">
          <SelectPrimitive.Value placeholder={placeholder} />
        </span>
        <ChevronDown className="size-4 shrink-0 opacity-60" />
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-[min(var(--radix-select-content-available-height),320px)] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-lg border bg-surface shadow-lg data-[state=open]:animate-fade-in"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value || EMPTY}
                value={o.value || EMPTY}
                className="relative flex cursor-default select-none items-center rounded-md py-1.5 pl-2 pr-8 text-sm outline-none data-[highlighted]:bg-accent data-[disabled]:opacity-50"
              >
                <div className="min-w-0">
                  <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                  {o.hint && <div className="text-xs text-muted-foreground">{o.hint}</div>}
                </div>
                <SelectPrimitive.ItemIndicator className="absolute right-2">
                  <Check className="size-4 text-primary" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
