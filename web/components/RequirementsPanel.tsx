"use client";

import type { Requirement } from "@/lib/contracts";
import { EmptyState } from "./Panel";
import { RequirementStatusBadge } from "./badges";

export function RequirementsPanel({
  requirements,
  onExtract,
  extracting = false,
  unavailableReason,
}: {
  requirements: Requirement[];
  onExtract?: (() => Promise<void>) | undefined;
  extracting?: boolean;
  unavailableReason?: string | undefined;
}) {
  const unverified = requirements.filter(
    (requirement) => requirement.status === "Unverified",
  ).length;
  const violated = requirements.filter(
    (requirement) => requirement.status === "Violated",
  ).length;

  return (
    <div className="flex flex-col gap-3" data-testid="requirements-panel">
      <div className="flex flex-wrap items-center gap-2 text-xs text-ink-dim">
        <span>{requirements.length} requirement(s)</span>
        {unverified > 0 ? (
          <span className="text-amber-400">{unverified} unverified</span>
        ) : null}
        {violated > 0 ? (
          <span className="font-semibold text-red-400">{violated} violated</span>
        ) : null}
        <span>Requirements are never marked satisfied without evidence.</span>
      </div>

      {requirements.length === 0 ? (
        <div className="flex flex-col gap-2">
          <EmptyState
            message="No requirements extracted yet."
            hint={
              unavailableReason ??
              "Requirements are derived from the task goal and re-checked after each patch."
            }
          />
          {onExtract ? (
            <button
              type="button"
              data-testid="extract-requirements"
              onClick={() => void onExtract()}
              disabled={extracting}
              className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-line-strong disabled:cursor-not-allowed disabled:opacity-60"
            >
              {extracting ? "Extracting requirements…" : "Extract requirements"}
            </button>
          ) : null}
        </div>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {requirements.map((requirement) => (
            <li
              key={requirement.requirement_id}
              data-testid={`requirement-${requirement.requirement_id}`}
              className="flex flex-col gap-2 rounded-lg border border-line bg-surface px-4 py-3.5"
            >
              <div className="flex flex-wrap items-center gap-2">
                <RequirementStatusBadge status={requirement.status} />
                <span
                  className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase ${
                    requirement.mandatory
                      ? "border-red-700/60 bg-red-950/60 text-red-300"
                      : "border-line bg-panel text-ink-dim"
                  }`}
                >
                  {requirement.mandatory ? "Mandatory" : "Optional"}
                </span>
                <span className="font-mono text-[11px] text-ink-dim">
                  {requirement.requirement_id}
                </span>
              </div>

              <p className="text-sm text-ink">{requirement.text}</p>

              {requirement.evidence && requirement.evidence.length > 0 ? (
                <div className="rounded-md border border-line bg-panel px-3 py-2">
                  <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
                    Evidence
                  </p>
                  <ul className="mt-1 flex flex-col gap-1">
                    {requirement.evidence.map((item) => (
                      <li
                        key={item}
                        className="font-mono text-xs leading-relaxed break-words text-ink-muted"
                      >
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-xs font-medium text-amber-400">
                  No evidence recorded — this requirement cannot be considered met.
                </p>
              )}

              {requirement.notes ? (
                <p className="text-xs text-ink-dim">{requirement.notes}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
