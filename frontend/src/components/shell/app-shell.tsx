"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronsLeft, ChevronsRight, LogOut, Menu, Monitor, Moon, Search, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { PoweredBy, Wordmark } from "@/components/brand";
import { Dot, Kbd } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useLiveCalls } from "@/lib/live";
import { useMe, useOverview } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { isCurrent, NAV } from "./nav";
import { UIProvider, useUI } from "./ui-context";

const COLLAPSE_KEY = "uvs.sidebar.collapsed";

function useCollapsed(): [boolean, (v: boolean) => void] {
  const value = useSyncExternalStore(
    (cb) => {
      window.addEventListener("storage", cb);
      return () => window.removeEventListener("storage", cb);
    },
    () => {
      try {
        return localStorage.getItem(COLLAPSE_KEY) === "1";
      } catch {
        return false;
      }
    },
    () => false,
  );
  const set = (v: boolean) => {
    try {
      localStorage.setItem(COLLAPSE_KEY, v ? "1" : "0");
    } catch {
      // storage unavailable; collapse just won't persist
    }
    window.dispatchEvent(new StorageEvent("storage"));
  };
  return [value, set];
}

/** "G then A" style navigation, ignored while typing in a field. */
function useGoShortcuts() {
  const router = useRouter();
  useEffect(() => {
    let armed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey || t?.closest("input, textarea, select, [contenteditable=true]")) return;
      const key = e.key.toLowerCase();
      if (armed) {
        armed = false;
        const hit = NAV.find((n) => n.shortcut.split(" ")[1]?.toLowerCase() === key);
        if (hit) {
          e.preventDefault();
          router.push(hit.href);
        }
        return;
      }
      if (key === "g") {
        armed = true;
        clearTimeout(timer);
        timer = setTimeout(() => (armed = false), 1200);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      clearTimeout(timer);
    };
  }, [router]);
}

function NavLinks({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const overview = useOverview();
  const active = overview.data?.active_calls ?? 0;
  return (
    <nav className="space-y-0.5" aria-label="Main">
      {NAV.map((n) => {
        const current = isCurrent(pathname, n.href);
        const link = (
          <Link
            key={n.href}
            href={n.href}
            onClick={onNavigate}
            aria-current={current ? "page" : undefined}
            className={cn(
              "group flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
              current && "bg-accent text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            <n.icon className={cn("size-4 shrink-0", current && "text-primary")} />
            {!collapsed && <span className="flex-1 truncate">{n.label}</span>}
            {!collapsed && n.href === "/calls" && active > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full bg-success-soft px-1.5 text-[11px] text-success">
                <Dot pulse /> {active}
              </span>
            )}
          </Link>
        );
        return collapsed ? (
          <Tooltip key={n.href} content={n.label} side="right">
            {link}
          </Tooltip>
        ) : (
          link
        );
      })}
    </nav>
  );
}

function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const me = useMe();
  const router = useRouter();
  const qc = useQueryClient();
  const { theme, setTheme } = useTheme();
  const initial = (me.data?.username ?? "?").slice(0, 1).toUpperCase();

  async function signOut() {
    try {
      await api.logout();
    } finally {
      router.replace("/login");
      qc.clear();
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex h-9 w-full items-center gap-2 rounded-md px-1.5 text-left text-[13px] hover:bg-accent",
          collapsed && "justify-center px-0",
        )}
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[11px] font-semibold text-primary">
          {initial}
        </span>
        {!collapsed && <span className="flex-1 truncate font-medium">{me.data?.username ?? "…"}</span>}
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-52">
        <div className="px-2 py-1.5 text-xs text-muted-foreground">Signed in as {me.data?.username}</div>
        <DropdownMenuSeparator />
        {(
          [
            ["light", Sun, "Light"],
            ["dark", Moon, "Dark"],
            ["system", Monitor, "System"],
          ] as const
        ).map(([value, Icon, label]) => (
          <DropdownMenuItem key={value} onSelect={() => setTheme(value)}>
            <Icon /> {label}
            {theme === value && <span className="ml-auto text-xs text-primary">Active</span>}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={signOut}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SearchButton({ collapsed }: { collapsed: boolean }) {
  const { openCommand } = useUI();
  return (
    <button
      onClick={openCommand}
      className={cn(
        "flex h-8 w-full items-center gap-2 rounded-md border bg-surface px-2 text-[13px] text-muted-foreground shadow-xs hover:text-foreground",
        collapsed && "justify-center px-0",
      )}
      aria-label="Open command menu"
    >
      <Search className="size-3.5" />
      {!collapsed && (
        <>
          <span className="flex-1 text-left">Search…</span>
          <Kbd>⌘K</Kbd>
        </>
      )}
    </button>
  );
}

function SidebarBody({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col gap-4 p-3">
      <Link href="/" onClick={onNavigate} className={cn("flex h-8 items-center px-1", collapsed && "justify-center px-0")}>
        <Wordmark compact={collapsed} />
      </Link>
      <SearchButton collapsed={collapsed} />
      <NavLinks collapsed={collapsed} onNavigate={onNavigate} />
      <div className="mt-auto space-y-2">
        <AccountMenu collapsed={collapsed} />
        <div className={cn("border-t px-1.5 pt-2.5", collapsed && "flex justify-center px-0")}>
          <PoweredBy compact={collapsed} />
        </div>
      </div>
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useCollapsed();
  const [mobileOpen, setMobileOpen] = useState(false);
  useLiveCalls();
  useGoShortcuts();

  return (
    <div className="flex min-h-dvh">
      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 border-r bg-surface-2/60 transition-[width] duration-150 md:block",
          collapsed ? "w-[60px]" : "w-60",
        )}
      >
        <SidebarBody collapsed={collapsed} />
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="absolute -right-3 top-14 z-10 flex size-6 items-center justify-center rounded-full border bg-surface text-muted-foreground shadow-xs hover:text-foreground"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronsRight className="size-3.5" /> : <ChevronsLeft className="size-3.5" />}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-12 items-center justify-between border-b bg-background/85 px-3 backdrop-blur md:hidden">
          <DialogPrimitive.Root open={mobileOpen} onOpenChange={setMobileOpen}>
            <DialogPrimitive.Trigger className="rounded-md p-1.5 hover:bg-accent" aria-label="Open menu">
              <Menu className="size-5" />
            </DialogPrimitive.Trigger>
            <DialogPrimitive.Portal>
              <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40" />
              <DialogPrimitive.Content className="fixed inset-y-0 left-0 z-50 w-64 border-r bg-surface shadow-xl outline-none data-[state=open]:animate-fade-in">
                <DialogPrimitive.Title className="sr-only">Menu</DialogPrimitive.Title>
                <DialogPrimitive.Description className="sr-only">Main navigation</DialogPrimitive.Description>
                <SidebarBody collapsed={false} onNavigate={() => setMobileOpen(false)} />
              </DialogPrimitive.Content>
            </DialogPrimitive.Portal>
          </DialogPrimitive.Root>
          <Wordmark />
          <span className="w-8" />
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <UIProvider>
      <Shell>{children}</Shell>
    </UIProvider>
  );
}

/** Standard page header: title, optional description and actions. */
export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-end justify-between gap-3", className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Page({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-6xl space-y-6 px-4 py-6 md:px-8 md:py-8", className)}>{children}</div>;
}
