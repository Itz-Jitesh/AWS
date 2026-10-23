import type { ReactNode } from "react";

export function Panel({
  title,
  description,
  actions,
  children,
  testId,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <section
      data-testid={testId}
      className="flex flex-col rounded-xl border border-line bg-panel"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-sm text-ink-muted">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      <div className="flex-1 px-5 py-4">{children}</div>
    </section>
  );
}

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong bg-surface px-4 py-6 text-center">
      <p className="text-sm text-ink-muted">{message}</p>
      {hint ? <p className="mt-1 text-xs text-ink-dim">{hint}</p> : null}
    </div>
  );
}

export function Banner({
  tone,
  title,
  children,
  testId,
}: {
  tone: "danger" | "warning" | "info" | "success";
  title: string;
  children?: ReactNode;
  testId?: string;
}) {
  const tones = {
    danger: "border-red-700/60 bg-red-950/70 text-red-200",
    warning: "border-amber-700/60 bg-amber-950/60 text-amber-200",
    info: "border-sky-700/50 bg-sky-950/60 text-sky-200",
    success: "border-emerald-700/60 bg-emerald-950/70 text-emerald-200",
  } as const;

  return (
    <div
      data-testid={testId}
      role={tone === "danger" ? "alert" : "status"}
      className={`rounded-lg border px-4 py-3 ${tones[tone]}`}
    >
      <p className="text-sm font-semibold">{title}</p>
      {children ? (
        <div className="mt-1 text-sm opacity-90 [&>p+p]:mt-1">{children}</div>
      ) : null}
    </div>
  );
}
