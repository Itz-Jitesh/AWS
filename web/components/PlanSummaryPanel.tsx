"use client";

import type { PlanSummary } from "@/lib/contracts";
import { shortDigest } from "@/lib/ui";
import { Banner, EmptyState } from "./Panel";
import { RiskBadge } from "./badges";

interface CountTile {
  key: "create" | "update" | "replace" | "destroy";
  label: string;
}

const TILES: CountTile[] = [
  { key: "create", label: "Create" },
  { key: "update", label: "Update" },
  { key: "replace", label: "Replace" },
  { key: "destroy", label: "Destroy" },
];

function tileClass(key: CountTile["key"], value: number): string {
  if (value === 0) return "border-line bg-surface text-ink-dim";
  if (key === "destroy") return "border-red-600 bg-red-950/70 text-red-300";
  if (key === "replace") return "border-amber-700/50 bg-surface text-amber-300";
  if (key === "update") return "border-sky-700/50 bg-surface text-sky-300";
  return "border-emerald-700/50 bg-surface text-emerald-300";
}

export function PlanSummaryPanel({
  planSummary,
}: {
  planSummary: PlanSummary | null;
}) {
  if (!planSummary) {
    return (
      <div data-testid="plan-summary">
        <EmptyState
          message="No plan captured yet."
          hint="The plan digest is required before approval can be enabled."
        />
      </div>
    );
  }

  const destructiveCount = planSummary.destructive_actions.length;

  return (
    <div className="flex flex-col gap-4" data-testid="plan-summary">
      {planSummary.destroy > 0 || planSummary.replace > 0 ? (
        <Banner tone="danger" title="Destructive changes in this plan" testId="destroy-banner">
          <p>
            {planSummary.destroy} destroy, {planSummary.replace} replace. Every
            destructive action is listed below and must be reviewed before approval.
          </p>
        </Banner>
      ) : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {TILES.map((tile) => (
          <div
            key={tile.key}
            data-testid={`plan-count-${tile.key}`}
            className={`rounded-lg border px-3 py-3 ${tileClass(tile.key, planSummary[tile.key])}`}
          >
            <p className="text-2xl font-semibold tabular-nums">
              {planSummary[tile.key]}
            </p>
            <p className="mt-0.5 text-[11px] font-semibold tracking-wide uppercase">
              {tile.label}
            </p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-line bg-surface px-3 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
            Plan digest (sha256)
          </p>
          <p
            className={`text-[11px] font-semibold tracking-wide uppercase ${
              planSummary.has_changes ? "text-emerald-300" : "text-ink-dim"
            }`}
          >
            {planSummary.has_changes ? "Changes present" : "No changes"}
          </p>
        </div>
        <p
          data-testid="plan-digest"
          className="mt-1 font-mono text-xs break-all text-ink-muted"
          title={planSummary.plan_digest}
        >
          {planSummary.plan_digest}
        </p>
        <p className="mt-1 font-mono text-[11px] text-ink-dim">
          {shortDigest(planSummary.plan_digest)} · approval is bound to this exact
          value
        </p>
      </div>

      {destructiveCount === 0 ? (
        <p className="text-xs text-ink-dim">
          No destroy or replace actions detected in this plan.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
            Destructive actions ({destructiveCount})
          </p>
          <ul className="flex flex-col gap-2">
            {planSummary.destructive_actions.map((action) => (
              <li
                key={action.address}
                data-testid={`destructive-${action.address}`}
                className="rounded-lg border border-red-700/50 bg-red-950/40 px-3 py-2.5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <RiskBadge risk={action.risk} />
                  <span className="font-mono text-sm text-red-100">
                    {action.address}
                  </span>
                </div>
                <p className="mt-1.5 font-mono text-xs text-red-200/90">
                  {action.actions.join(" → ")}
                </p>
                {action.reason ? (
                  <p className="mt-1 text-xs text-red-200/80">{action.reason}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
