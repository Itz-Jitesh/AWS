"use client";

import type { Operation, PlanProofApi, SupportLevel } from "@/lib/api";

const BACKEND_LABELS: Record<PlanProofApi["backend"], string> = {
  mock: "Mock services (demonstration data)",
  "worker-direct": "Live worker service (direct)",
  orchestration: "Live API (orchestration, unverified)",
};

const OPERATION_LABELS: Record<Operation, string> = {
  createTask: "Task creation / ingest",
  getWorkspace: "Task read (workspace)",
  runCheckSuite: "Check suite",
  findings: "Findings",
  extractRequirements: "Requirements extraction",
  generatePatch: "Patch generation",
  planSummary: "Plan classification",
  capturePlan: "Plan capture",
  approveTask: "Approval",
  getEvidenceReport: "Evidence report export",
};

const LEVEL_LABELS: Record<SupportLevel, string> = {
  available: "available",
  unverified: "unverified",
  unavailable: "unavailable",
};

export function ServiceNotice({ api }: { api: PlanProofApi }) {
  const notes = api.operationNotes?.() ?? {};
  const entries = (Object.keys(api.support) as Operation[])
    .map((operation) => ({
      operation,
      level: api.support[operation],
      detail: notes[operation]?.detail,
    }))
    .filter((entry) => entry.level !== "available");

  if (entries.length === 0) return null;

  return (
    <section
      data-testid="service-notice"
      className="rounded-xl border border-amber-700/50 bg-amber-950/40 px-5 py-4"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="text-[11px] font-semibold tracking-wide text-amber-300 uppercase">
          Service status
        </p>
        <p className="text-xs text-amber-200/80">{BACKEND_LABELS[api.backend]}</p>
      </div>
      <p className="mt-1 text-xs text-ink-muted">
        Live mode is active; demonstration data is never substituted for a live
        response. Operations below are limited by contracts that are missing or not
        yet implemented.
      </p>
      <ul className="mt-2 flex flex-col gap-1">
        {entries.map((entry) => (
          <li key={entry.operation} className="flex flex-wrap gap-x-2 text-xs">
            <span className="font-semibold text-ink-muted">
              {OPERATION_LABELS[entry.operation]}
            </span>{" "}
            <span
              className={`font-medium ${
                entry.level === "unavailable" ? "text-red-300" : "text-amber-300"
              }`}
            >
              ({LEVEL_LABELS[entry.level]})
            </span>
            {entry.detail ? (
              <span className="text-ink-dim">{entry.detail}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
