"use client";

import type { CheckRun } from "@/lib/contracts";
import { formatDuration, formatTimestamp, statusRank } from "@/lib/ui";
import { EmptyState } from "./Panel";
import { StatusBadge } from "./badges";

export function CheckRunList({ checks }: { checks: CheckRun[] }) {
  const sorted = [...checks].sort((a, b) => statusRank(a.status) - statusRank(b.status));

  const passed = checks.filter((check) => check.status === "Passed").length;
  const failed = checks.filter((check) => check.status === "Failed").length;
  const unverified = checks.filter(
    (check) => check.status === "UnableToVerify" || check.status === "NotConfigured",
  ).length;

  return (
    <div className="flex flex-col gap-3" data-testid="check-run-list">
      <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-ink-dim">
        <span className="text-emerald-400">{passed} passed</span>
        <span className="text-red-400">{failed} failed</span>
        <span className="text-amber-400">{unverified} not configured / unverified</span>
        <span>
          {checks.length} check(s) in the last full suite run
        </span>
      </div>

      {checks.length === 0 ? (
        <EmptyState
          message="No check suite has run for this task."
          hint="Run checks to collect fmt, validate, plan, Checkov and OPA results."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {sorted.map((check) => (
            <li
              key={check.check_id}
              data-testid={`check-${check.check_id}`}
              className="rounded-lg border border-line bg-surface px-4 py-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={check.status} testId={`check-status-${check.check_id}`} />
                <span className="font-mono text-sm text-ink">{check.tool}</span>
                <span className="ml-auto flex flex-wrap items-center gap-3 text-[11px] text-ink-dim">
                  <span>{formatTimestamp(check.started_at)}</span>
                  <span>{formatDuration(check.duration_ms)}</span>
                  <span className="font-mono">
                    {check.tool_version ? `v${check.tool_version}` : "version unknown"}
                  </span>
                </span>
              </div>

              <p className="mt-1.5 text-sm text-ink-muted">{check.summary}</p>

              {check.limitations && check.limitations.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1 border-l-2 border-amber-700/60 pl-3">
                  {check.limitations.map((limitation) => (
                    <li key={limitation} className="text-xs text-amber-300/90">
                      {limitation}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
