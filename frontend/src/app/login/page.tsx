"use client";

import { ArrowRight, Lock } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { LogoMark, PoweredBy } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

function safeNext(raw: string | null): string {
  // Only same-site paths; never "//evil.example" or absolute URLs.
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.login(username.trim(), password);
      router.replace(safeNext(params.get("next")));
      router.refresh();
    } catch (err) {
      setPassword("");
      setError(
        err instanceof ApiError && err.status === 401
          ? "Wrong username or password."
          : err instanceof Error
            ? err.message
            : "Couldn't sign in.",
      );
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field label="Username" htmlFor="username">
        <Input
          id="username"
          autoComplete="username"
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="h-9"
          required
        />
      </Field>
      <Field label="Password" htmlFor="password">
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-9"
          required
        />
      </Field>
      {error && (
        <p className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <Button
        type="submit"
        variant="primary"
        size="lg"
        className="w-full"
        loading={busy}
        disabled={!username || !password}
      >
        Sign in <ArrowRight />
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="relative flex min-h-dvh flex-col items-center justify-center overflow-hidden px-4 py-10">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 [background:radial-gradient(60rem_30rem_at_50%_-10%,var(--color-primary-soft),transparent_70%)]"
      />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center text-center">
          <LogoMark className="size-10" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">Ulai Voice Studio</h1>
          <p className="mt-1 text-sm text-muted-foreground">Sign in to build and run your voice agents.</p>
        </div>
        <div className="rounded-xl border bg-surface p-6 shadow-sm">
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
        <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <Lock className="size-3" /> Single admin account. Access is set in the server&apos;s configuration.
        </p>
      </div>
      <PoweredBy className="relative mt-10" />
    </main>
  );
}
