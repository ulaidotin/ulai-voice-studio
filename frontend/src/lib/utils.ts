import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { CallDirection, CallStatus } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${sec.toString().padStart(2, "0")}s`;
  return `${sec}s`;
}

/** mm:ss for a running clock. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)
    .toString()
    .padStart(2, "0")}:${(s % 60).toString().padStart(2, "0")}`;
}

export function elapsedLabel(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  return clock(ms / 1000);
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function timeAgo(iso: string): string {
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 45) return "just now";
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 7 * 86400) return rtf.format(Math.round(diff / 86400), "day");
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Groups +14155550123 as +1 415 555 0123 for reading; leaves anything unexpected untouched. */
export function formatPhone(n: string | null | undefined): string {
  if (!n) return "";
  const m = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(n);
  if (m) return `+1 ${m[1]} ${m[2]} ${m[3]}`;
  const in91 = /^\+91(\d{5})(\d{5})$/.exec(n);
  if (in91) return `+91 ${in91[1]} ${in91[2]}`;
  return n;
}

export const STATUS_LABEL: Record<CallStatus, string> = {
  queued: "Queued",
  ringing: "Ringing",
  in_progress: "In progress",
  completed: "Completed",
  no_answer: "No answer",
  failed: "Failed",
};

export const DIRECTION_LABEL: Record<CallDirection, string> = {
  web: "Web",
  inbound: "Inbound",
  outbound: "Outbound",
};

export function plural(n: number, one: string, many = `${one}s`) {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

/** Placeholders like {{customer_name}} used in a text. */
export function placeholders(text: string): string[] {
  return [...text.matchAll(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g)].map((m) => m[1]!);
}
