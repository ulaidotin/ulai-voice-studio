import { cn } from "@/lib/utils";

/** The studio's mark: a waveform in a rounded square. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <g className="stroke-primary-foreground" strokeWidth="2.4" strokeLinecap="round">
        <path d="M9 13v6" />
        <path d="M13 9.5v13" />
        <path d="M17 12v8" />
        <path d="M21 8v16" />
        <path d="M25 13.5v5" />
      </g>
    </svg>
  );
}

export function Wordmark({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <LogoMark />
      {!compact && (
        <span className="leading-tight">
          <span className="block text-sm font-semibold tracking-tight">Ulai Voice Studio</span>
        </span>
      )}
    </span>
  );
}

/** "Powered by Ulai Voice Infra". Shown on the login page, the sidebar and every call panel. */
export function PoweredBy({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <a
      href="https://ulai.in"
      target="_blank"
      rel="noreferrer"
      className={cn(
        "group inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground",
        className,
      )}
      title="Powered by Ulai Voice Infra"
    >
      <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden>
        <path
          d="M3 6.5v3M6 4.5v7M9 6v4M12 3.5v9"
          className="stroke-primary"
          strokeWidth="1.6"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      {compact ? (
        <span className="font-medium">Ulai Voice Infra</span>
      ) : (
        <span>
          Powered by <span className="font-medium text-foreground/80 group-hover:text-foreground">Ulai Voice Infra</span>
        </span>
      )}
    </a>
  );
}
