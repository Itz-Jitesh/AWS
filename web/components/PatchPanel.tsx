"use client";

import type { Patch } from "@/lib/contracts";
import { shortDigest } from "@/lib/ui";
import { DiffViewer } from "./DiffViewer";
import { EmptyState } from "./Panel";

export function PatchPanel({ patch }: { patch: Patch | null }) {
  if (!patch) {
    return (
      <div data-testid="patch-panel">
        <EmptyState
          message="No patch proposed yet."
          hint="Generate a patch to see the minimal unified diff for this goal."
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="patch-panel">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-muted">
        <span className="font-mono text-ink">{patch.patch_id}</span>
        <span>
          Base <span className="font-mono">{shortDigest(patch.base_digest)}</span>
        </span>
        {patch.model_id ? (
          <span>
            Model <span className="font-mono">{patch.model_id}</span>
          </span>
        ) : null}
        <span className="flex flex-wrap items-center gap-1.5">
          {patch.files_changed.map((file) => (
            <span
              key={file}
              className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink-muted"
            >
              {file}
            </span>
          ))}
        </span>
      </div>

      <div className="rounded-lg border border-line bg-surface px-4 py-3">
        <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
          Rationale
        </p>
        <p className="mt-1 text-sm leading-relaxed text-ink-muted">
          {patch.rationale}
        </p>
      </div>

      {patch.warnings && patch.warnings.length > 0 ? (
        <div
          className="rounded-lg border border-amber-700/60 bg-amber-950/60 px-4 py-3"
          role="status"
        >
          <p className="text-xs font-semibold tracking-wide text-amber-300 uppercase">
            Patch warnings
          </p>
          <ul className="mt-1 flex flex-col gap-1">
            {patch.warnings.map((warning) => (
              <li key={warning} className="text-xs text-amber-200/90">
                {warning}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <DiffViewer diff={patch.unified_diff} />
    </div>
  );
}
