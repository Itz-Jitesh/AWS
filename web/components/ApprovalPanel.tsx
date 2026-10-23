"use client";

import { useState } from "react";
import type { ApprovalRecord } from "@/lib/api";
import type { PlanSummary } from "@/lib/contracts";
import { formatTimestamp } from "@/lib/ui";
import { Banner } from "./Panel";

export function ApprovalPanel({
  planSummary,
  approval,
  onApprove,
}: {
  planSummary: PlanSummary | null;
  approval: ApprovalRecord | null;
  onApprove: (planDigest: string) => Promise<void>;
}) {
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const digest = planSummary?.plan_digest ?? "";
  const canApprove = digest.length > 0 && !approving && !approval;

  async function handleApprove() {
    setError(null);
    setApproving(true);
    try {
      await onApprove(digest);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Approval failed unexpectedly.",
      );
    } finally {
      setApproving(false);
    }
  }

  if (approval) {
    return (
      <div className="flex flex-col gap-3" data-testid="approval-panel">
        <Banner tone="success" title="Approval recorded">
          <p>
            This task was approved for the exact plan digest below. Any change to the
            plan invalidates the approval.
          </p>
        </Banner>
        <dl className="flex flex-col gap-2 rounded-lg border border-emerald-800/50 bg-surface px-4 py-3 text-sm">
          <div>
            <dt className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
              Approved plan digest
            </dt>
            <dd
              data-testid="approved-digest"
              className="mt-1 font-mono text-xs break-all text-emerald-200"
            >
              {approval.approved_plan_digest}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
              Approved at
            </dt>
            <dd className="mt-1 font-mono text-xs text-ink-muted">
              {formatTimestamp(approval.approved_at)}
            </dd>
          </div>
        </dl>
        <p className="text-xs text-ink-dim">
          Live apply is not enabled in the MVP, so no infrastructure is changed by
          this approval.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="approval-panel">
      {!digest ? (
        <Banner tone="warning" title="Plan digest missing" testId="missing-digest">
          <p>
            No plan has been captured for this task. Approval stays disabled until a
            plan digest exists.
          </p>
        </Banner>
      ) : (
        <div className="rounded-lg border border-line bg-surface px-4 py-3">
          <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
            Plan digest to approve (sha256)
          </p>
          <p
            data-testid="approval-digest"
            className="mt-1 font-mono text-xs break-all text-ink"
            title={digest}
          >
            {digest}
          </p>
          <p className="mt-1.5 text-xs text-ink-dim">
            Approval is invalidated automatically if this digest changes.
          </p>
        </div>
      )}

      {planSummary && planSummary.destructive_actions.length > 0 ? (
        <Banner tone="danger" title="Review destructive actions first">
          <ul className="mt-1 flex flex-col gap-1">
            {planSummary.destructive_actions.map((action) => (
              <li key={action.address} className="font-mono text-xs">
                {action.address} · {action.actions.join(" → ")} · {action.risk} risk
              </li>
            ))}
          </ul>
        </Banner>
      ) : null}

      {error ? (
        <Banner tone="danger" title="Approval rejected" testId="approval-error">
          <p>{error}</p>
        </Banner>
      ) : null}

      <div className="flex flex-col gap-2">
        <button
          type="button"
          data-testid="approve-button"
          disabled={!canApprove}
          onClick={handleApprove}
          className="w-full rounded-lg border border-accent/70 bg-accent/15 px-4 py-2.5 text-sm font-semibold text-ink transition-colors hover:bg-accent/25 disabled:cursor-not-allowed disabled:border-line disabled:bg-surface disabled:text-ink-dim"
        >
          {approving ? "Recording approval…" : "Approve this plan"}
        </button>
        <p className="text-xs text-ink-dim">
          {!digest
            ? "Enable approval by capturing a plan first."
            : "Approving records consent for this exact plan only. It does not apply infrastructure."}
        </p>
      </div>
    </div>
  );
}
