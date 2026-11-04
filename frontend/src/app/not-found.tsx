import Link from "next/link";

import { LogoMark } from "@/components/brand";

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 px-4 text-center">
      <LogoMark className="size-9" />
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="text-sm text-muted-foreground">That page doesn&apos;t exist or was removed.</p>
      <Link href="/" className="text-sm font-medium text-primary hover:underline">
        Back to overview
      </Link>
    </main>
  );
}
