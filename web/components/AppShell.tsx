"use client";

import Link from "next/link";
import type { ReactNode } from "react";

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="flex h-7 w-7 items-center justify-center rounded-md border border-accent/50 bg-accent/15"
      >
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none">
          <path
            d="M8 1.5 14 5v6l-6 3.5L2 11V5l6-3.5Z"
            stroke="currentColor"
            className="text-accent"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <path
            d="M5.5 8.2 7.2 10l3.4-4"
            stroke="currentColor"
            className="text-emerald-400"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="text-[15px] font-semibold tracking-tight text-ink">
        PlanProof
      </span>
    </span>
  );
}

export function AppShell({
  children,
  dataSourceLabel,
}: {
  children: ReactNode;
  dataSourceLabel?: string;
}) {
  const usingMocks = !process.env.NEXT_PUBLIC_API_BASE_URL;

  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-background/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-6 py-3.5">
          <Link href="/" className="rounded-md">
            <Logo />
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <Link
              href="/"
              className="rounded-md px-3 py-1.5 text-ink-muted transition-colors hover:bg-surface hover:text-ink"
            >
              New task
            </Link>
            <Link
              href="/tasks/demo"
              className="rounded-md px-3 py-1.5 text-ink-muted transition-colors hover:bg-surface hover:text-ink"
            >
              Demo workspace
            </Link>
          </nav>
          <span
            data-testid="data-source"
            className={`rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide uppercase ${
              usingMocks
                ? "border-amber-700/60 bg-amber-950/60 text-amber-300"
                : "border-emerald-700/60 bg-emerald-950/70 text-emerald-300"
            }`}
          >
            {dataSourceLabel ?? (usingMocks ? "Mock services" : "Live API")}
          </span>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">{children}</main>

      <footer className="border-t border-line px-6 py-5">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-1 text-xs text-ink-dim sm:flex-row sm:items-center sm:justify-between">
          <p>
            PlanProof never runs <code className="font-mono">terraform apply</code>{" "}
            in the MVP. Apply is out of scope.
          </p>
          <p>
            Check results are evidence, not a security guarantee. Approval is bound
            to the exact plan digest.
          </p>
        </div>
      </footer>
    </div>
  );
}
