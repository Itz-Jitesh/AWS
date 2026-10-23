"use client";

import { useState } from "react";
import type { EvidenceReport } from "@/lib/api";
import { EmptyState } from "./Panel";

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function EvidencePanel({
  taskId,
  limitations,
  toolVersions,
  onDownload,
}: {
  taskId: string;
  limitations: string[];
  toolVersions: Record<string, string | null>;
  onDownload: () => Promise<EvidenceReport>;
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const toolEntries = Object.entries(toolVersions);

  async function handleDownload() {
    setError(null);
    setPending(true);
    try {
      const report = await onDownload();
      downloadJson(`planproof-report-${taskId}.json`, report);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Report export failed.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex flex-col gap-4" data-testid="evidence-panel">
      <div className="rounded-lg border border-line bg-surface px-4 py-3">
        <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
          Tool versions in the last suite run
        </p>
        {toolEntries.length === 0 ? (
          <p className="mt-1.5 text-xs text-ink-dim">No tool versions recorded yet.</p>
        ) : (
          <ul className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {toolEntries.map(([tool, version]) => (
              <li key={tool} className="flex justify-between gap-3 text-xs">
                <span className="font-mono text-ink-muted">{tool}</span>
                <span className={`font-mono ${version ? "text-ink" : "text-amber-400"}`}>
                  {version ?? "unknown"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg border border-line bg-surface px-4 py-3">
        <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
          Known limitations
        </p>
        {limitations.length === 0 ? (
          <EmptyState message="No limitations recorded." />
        ) : (
          <ul className="mt-2 flex flex-col gap-1.5">
            {limitations.map((limitation) => (
              <li
                key={limitation}
                className="flex gap-2 text-xs leading-relaxed text-ink-muted"
              >
                <span aria-hidden className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-400" />
                {limitation}
              </li>
            ))}
          </ul>
        )}
      </div>

      {error ? (
        <div role="alert" className="rounded-lg border border-red-700/60 bg-red-950/70 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-dim">
          The report records statuses, evidence, versions, the plan digest and
          limitations. It is not a security guarantee.
        </p>
        <button
          type="button"
          data-testid="download-report"
          onClick={handleDownload}
          disabled={pending}
          className="rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:border-line-strong disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "Preparing report…" : "Download evidence report"}
        </button>
      </div>
    </div>
  );
}
