"use client";

import { useMemo, useState } from "react";
import type { Finding } from "@/lib/contracts";
import { severityRank, statusRank } from "@/lib/ui";
import { EmptyState } from "./Panel";
import { SeverityBadge, StatusBadge } from "./badges";

function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => {
    const byStatus = statusRank(a.status) - statusRank(b.status);
    if (byStatus !== 0) return byStatus;
    const bySeverity = severityRank(a.severity) - severityRank(b.severity);
    if (bySeverity !== 0) return bySeverity;
    return a.rule_id.localeCompare(b.rule_id);
  });
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <article
      data-testid={`finding-${finding.finding_id}`}
      className="flex flex-col gap-3 rounded-lg border border-line bg-surface px-4 py-3.5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        <StatusBadge status={finding.status} />
        <span className="font-mono text-xs text-ink-muted">{finding.rule_id}</span>
        <span className="rounded border border-line px-1.5 py-0.5 text-[11px] tracking-wide text-ink-dim uppercase">
          {finding.rule_source}
        </span>
        <span className="ml-auto font-mono text-[11px] text-ink-dim">
          {finding.fingerprint.slice(0, 12)}
        </span>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-ink">{finding.title}</h3>
        {finding.description ? (
          <p className="mt-1 text-sm text-ink-muted">{finding.description}</p>
        ) : null}
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
        {finding.resource_address ? (
          <div className="flex gap-1.5">
            <dt className="text-ink-dim">Resource</dt>
            <dd className="font-mono text-ink-muted">{finding.resource_address}</dd>
          </div>
        ) : null}
        {finding.file_path ? (
          <div className="flex gap-1.5">
            <dt className="text-ink-dim">Location</dt>
            <dd className="font-mono text-ink-muted">
              {finding.file_path}
              {finding.line_start ? `:${finding.line_start}` : ""}
            </dd>
          </div>
        ) : null}
      </dl>

      <div className="rounded-md border border-line bg-panel px-3 py-2">
        <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
          Evidence
        </p>
        <p className="mt-1 font-mono text-xs leading-relaxed break-words text-ink-muted">
          {finding.evidence}
        </p>
      </div>

      {finding.remediation ? (
        <p className="text-xs text-ink-muted">
          <span className="font-semibold text-ink-dim">Remediation:</span>{" "}
          {finding.remediation}
        </p>
      ) : null}
    </article>
  );
}

export function FindingsList({
  findings,
  baseline,
  emptyMessage = "No findings recorded for this task yet.",
  unavailableReason,
}: {
  findings: Finding[];
  baseline?: Finding[];
  emptyMessage?: string;
  unavailableReason?: string;
}) {
  const [view, setView] = useState<"current" | "baseline">("current");
  const hasBaseline = Boolean(baseline && baseline.length > 0);
  const active = useMemo(
    () => (hasBaseline && view === "baseline" ? baseline ?? [] : findings),
    [hasBaseline, view, baseline, findings],
  );
  const sorted = useMemo(() => sortFindings(active), [active]);

  const counts = useMemo(() => {
    const total = { failed: 0, unverified: 0, passed: 0, other: 0 };
    for (const finding of active) {
      if (finding.status === "Failed") total.failed += 1;
      else if (finding.status === "UnableToVerify") total.unverified += 1;
      else if (finding.status === "Passed") total.passed += 1;
      else total.other += 1;
    }
    return total;
  }, [active]);

  return (
    <div className="flex flex-col gap-3" data-testid="findings-list">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {hasBaseline ? (
          <div
            role="tablist"
            aria-label="Finding snapshot"
            className="flex rounded-lg border border-line bg-surface p-1"
          >
            {(
              [
                { value: "current", label: "After patch" },
                { value: "baseline", label: "Baseline (before patch)" },
              ] as const
            ).map((tab) => (
              <button
                key={tab.value}
                type="button"
                role="tab"
                aria-selected={view === tab.value}
                onClick={() => setView(tab.value)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  view === tab.value
                    ? "bg-accent/20 text-ink"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        ) : (
          <span />
        )}

        <p className="font-mono text-[11px] text-ink-dim">
          <span className="text-red-400">{counts.failed} failed</span>
          {" · "}
          <span className="text-amber-400">{counts.unverified} unable to verify</span>
          {" · "}
          <span className="text-emerald-400">{counts.passed} passed</span>
          {counts.other > 0 ? ` · ${counts.other} other` : ""}
        </p>
      </div>

      {sorted.length === 0 ? (
        <EmptyState
          message={unavailableReason ? "Findings are unavailable in this mode." : emptyMessage}
          hint={unavailableReason ?? "Findings appear after the check suite runs."}
        />
      ) : (
        <div className="flex flex-col gap-2.5">
          {sorted.map((finding) => (
            <FindingRow key={finding.finding_id} finding={finding} />
          ))}
        </div>
      )}
    </div>
  );
}
