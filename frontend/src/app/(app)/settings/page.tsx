"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useSyncExternalStore } from "react";

import { PoweredBy } from "@/components/brand";
import { Page, PageHeader } from "@/components/shell/app-shell";
import { SystemStatus } from "@/components/status/system-status";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { cn } from "@/lib/utils";

const THEMES = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
] as const;

export default function SettingsPage() {
  const me = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const { theme, setTheme } = useTheme();
  // The theme is only known in the browser; avoid a mismatched first render.
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );

  async function signOut() {
    try {
      await api.logout();
    } finally {
      router.replace("/login");
      qc.clear();
    }
  }

  return (
    <Page className="max-w-3xl">
      <PageHeader title="Settings" />

      <Card>
        <CardHeader title="Account" description="This studio has a single admin account, set in the server's configuration." />
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
          <div className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary">
              {(me.data?.username ?? "?").slice(0, 1).toUpperCase()}
            </span>
            <div>
              <div className="text-sm font-medium">{me.data?.username ?? "…"}</div>
              <div className="text-xs text-muted-foreground">Administrator</div>
            </div>
          </div>
          <Button onClick={signOut}>
            <LogOut /> Sign out
          </Button>
        </div>
        <p className="border-t px-4 py-3 text-xs text-muted-foreground">
          To change the password, generate a new hash with{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono">python -m app.auth hash-password</code>, set it as{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono">ADMIN_PASSWORD_HASH</code> and restart the backend.
        </p>
      </Card>

      <Card>
        <CardHeader title="Appearance" />
        <div className="grid grid-cols-3 gap-2 p-4" role="radiogroup" aria-label="Theme">
          {THEMES.map((t) => {
            const active = mounted && theme === t.value;
            return (
              <button
                key={t.value}
                role="radio"
                aria-checked={active}
                onClick={() => setTheme(t.value)}
                className={cn(
                  "flex flex-col items-center gap-2 rounded-lg border px-3 py-4 text-sm transition-colors hover:bg-surface-2",
                  active && "border-primary bg-primary-soft/40 ring-1 ring-primary",
                )}
              >
                <t.icon className="size-5 text-muted-foreground" />
                {t.label}
              </button>
            );
          })}
        </div>
      </Card>

      <SystemStatus />

      <div className="flex justify-center pt-2">
        <PoweredBy />
      </div>
    </Page>
  );
}
