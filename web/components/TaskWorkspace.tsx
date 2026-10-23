"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, type TaskWorkspace as Workspace } from "@/lib/api";
import { getApiClient } from "@/lib/client";
import { collectLimitations, collectToolVersions } from "@/lib/report";
import { isBlockingStatus } from "@/lib/ui";
import { ApprovalPanel } from "./ApprovalPanel";
import { Banner, EmptyState, Panel } from "./Panel";
import { CheckRunList } from "./CheckRunList";
import { EvidencePanel } from "./EvidencePanel";
import { FindingsList } from "./FindingsList";
import { PatchPanel } from "./PatchPanel";
import { PlanSummaryPanel } from "./PlanSummaryPanel";
import { RequirementsPanel } from "./RequirementsPanel";
import { StateBadge } from "./badges";

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; message: string; notFound: boolean }
  | { kind: "ready"; workspace: Workspace };

function toErrorState(error: unknown): LoadState {
  return {
    kind: "error",
    message: error instanceof Error ? error.message : "Failed to load task.",
    notFound: error instanceof ApiError && error.kind === "not_found",
  };
}

export function TaskWorkspace({ taskId }: { taskId: string }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [busy, setBusy] = useState<"checks" | "patch" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const workspace = await getApiClient().getWorkspace(taskId);
      setState({ kind: "ready", workspace });
    } catch (error) {
      setState(toErrorState(error));
    }
  }, [taskId]);

  useEffect(() => {
    let cancelled = false;
    getApiClient()
      .getWorkspace(taskId)
      .then((workspace) => {
        if (!cancelled) setState({ kind: "ready", workspace });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState(toErrorState(error));
      });
    return () => {
      cancelled = true;
    };
  }, [taskId]);

  async function runChecks() {
    setActionError(null);
    setBusy("checks");
    try {
      await getApiClient().runCheckSuite(taskId);
      await refresh();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "The check suite failed to run.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function generatePatch() {
    setActionError(null);
    setBusy("patch");
    try {
      await getApiClient().generatePatch(taskId);
      await refresh();
    } catch (error) {
      setActionError(
        error instanceof Error ? error.message : "Patch generation failed.",
      );
    } finally {
      setBusy(null);
    }
  }

  async function approve(digest: string) {
    await getApiClient().approveTask(taskId, digest);
    await refresh();
  }

  if (state.kind === "loading") {
    return (
      <div className="flex flex-col gap-4" data-testid="workspace-loading">
        {[0, 1, 2].map((row) => (
          <div
            key={row}
            className="h-40 animate-pulse rounded-xl border border-line bg-panel"
          />
        ))}
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="flex flex-col gap-4" data-testid="workspace-error">
        <Banner
          tone={state.notFound ? "warning" : "danger"}
          title={state.notFound ? "Task not found" : "Failed to load task"}
        >
          <p>{state.message}</p>
        </Banner>
        <div className="flex gap-3">
          <Link
            href="/"
            className="rounded-lg border border-line px-4 py-2 text-sm text-ink-muted hover:border-line-strong hover:text-ink"
          >
            Create a new task
          </Link>
          <Link
            href="/tasks/demo"
            className="rounded-lg border border-line px-4 py-2 text-sm text-ink-muted hover:border-line-strong hover:text-ink"
          >
            Open the demo workspace
          </Link>
        </div>
      </div>
    );
  }

  const { workspace } = state;
  const { task, plan_summary: planSummary, approval } = workspace;

  const blockingChecks = workspace.checks.filter((check) =>
    isBlockingStatus(check.status),
  );
  const failedChecks = blockingChecks.filter((check) => check.status === "Failed");
  const unverifiedChecks = blockingChecks.filter(
    (check) => check.status !== "Failed",
  );
  const unverifiedMandatory = workspace.requirements.filter(
    (requirement) => requirement.mandatory && requirement.status === "Unverified",
  );
  const violated = workspace.requirements.filter(
    (requirement) => requirement.status === "Violated",
  );
  const destructive = planSummary?.destructive_actions ?? [];

  return (
    <div className="flex flex-col gap-5" data-testid="task-workspace">
      <header className="flex flex-col gap-4 rounded-xl border border-line bg-panel px-5 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="font-mono text-xs text-ink-dim">{task.task_id}</span>
          <StateBadge state={task.state} />
          <span className="rounded border border-line px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
            {task.mode} mode
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="run-checks"
              onClick={runChecks}
              disabled={busy !== null}
              className="rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-line-strong disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === "checks" ? "Running checks…" : "Run full check suite"}
            </button>
            <button
              type="button"
              data-testid="generate-patch"
              onClick={generatePatch}
              disabled={busy !== null || task.mode === "audit"}
              title={
                task.mode === "audit"
                  ? "Patch generation is only available in build mode."
                  : undefined
              }
              className="rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-background transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === "patch" ? "Generating patch…" : "Generate patch"}
            </button>
          </div>
        </div>

        <div>
          <p className="text-[11px] font-semibold tracking-wide text-ink-dim uppercase">
            Goal
          </p>
          <p className="mt-1 text-lg leading-snug font-medium text-ink">{task.goal}</p>
        </div>
      </header>

      {actionError ? (
        <Banner tone="danger" title="Action failed" testId="action-error">
          <p>{actionError}</p>
        </Banner>
      ) : null}

      <div className="flex flex-col gap-3">
        {failedChecks.length > 0 ? (
          <Banner tone="danger" title={`${failedChecks.length} mandatory check(s) failed`} testId="banner-failed-checks">
            <p>
              The task cannot advance to review until failing checks are repaired.
              Failed checks are never reported as passed.
            </p>
          </Banner>
        ) : null}
        {unverifiedChecks.length > 0 ? (
          <Banner tone="warning" title={`${unverifiedChecks.length} check(s) could not be verified`} testId="banner-unverified-checks">
            <p>
              {unverifiedChecks.map((check) => check.tool).join(", ")} could not be
              verified or was not configured. This is not a pass.
            </p>
          </Banner>
        ) : null}
        {unverifiedMandatory.length > 0 ? (
          <Banner tone="warning" title={`${unverifiedMandatory.length} mandatory requirement(s) unverified`} testId="banner-unverified-requirements">
            <p>These requirements are not claimed as met: </p>
            <ul className="mt-1 flex flex-col gap-0.5">
              {unverifiedMandatory.map((requirement) => (
                <li key={requirement.requirement_id} className="font-mono text-xs">
                  {requirement.requirement_id}: {requirement.text}
                </li>
              ))}
            </ul>
          </Banner>
        ) : null}
        {violated.length > 0 ? (
          <Banner tone="danger" title={`${violated.length} requirement(s) violated`} testId="banner-violated-requirements">
            <p>
              {violated.map((requirement) => requirement.text).join(" · ")}
            </p>
          </Banner>
        ) : null}
        {destructive.length > 0 ? (
          <Banner tone="danger" title="Destructive plan actions require review" testId="banner-destructive">
            <p>
              {destructive.map((action) => action.address).join(", ")} — listed with
              risk levels in the plan summary.
            </p>
          </Banner>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-12">
        <div className="flex flex-col gap-5 lg:col-span-7">
          <Panel
            title="Check suite"
            description="Last full run of fmt, init, validate, plan, Checkov and OPA."
            testId="panel-checks"
          >
            <CheckRunList checks={workspace.checks} />
          </Panel>

          <Panel
            title="Requirements"
            description="Extracted from the goal and re-checked after each patch."
            testId="panel-requirements"
          >
            <RequirementsPanel requirements={workspace.requirements} />
          </Panel>

          <Panel
            title="Findings"
            description="Normalized from Checkov, OPA and custom rules."
            testId="panel-findings"
          >
            <FindingsList
              findings={workspace.findings}
              baseline={workspace.baseline_findings}
            />
          </Panel>
        </div>

        <div className="flex flex-col gap-5 lg:col-span-5">
          <Panel
            title="Plan summary"
            description="Classified from terraform show -json output."
            testId="panel-plan"
          >
            <PlanSummaryPanel planSummary={planSummary} />
          </Panel>

          <Panel
            title="Approval"
            description="Human approval bound to the exact plan digest."
            testId="panel-approval"
          >
            <ApprovalPanel
              planSummary={planSummary}
              approval={approval}
              onApprove={approve}
            />
          </Panel>
        </div>
      </div>

      <Panel
        title="Proposed patch"
        description="Minimal unified diff. The repository is never rewritten wholesale."
        testId="panel-patch"
      >
        <PatchPanel patch={workspace.patch} />
      </Panel>

      <Panel
        title="Evidence report"
        description="Versions, statuses, digest and limitations for this task."
        testId="panel-evidence"
      >
        <EvidencePanel
          taskId={task.task_id}
          limitations={collectLimitations(workspace)}
          toolVersions={collectToolVersions(workspace.checks)}
          onDownload={() => getApiClient().getEvidenceReport(task.task_id)}
        />
      </Panel>

      {workspace.checks.length === 0 && !workspace.patch ? (
        <EmptyState
          message="This task has no artifacts yet."
          hint="Run the full check suite to populate findings, checks and the plan summary."
        />
      ) : null}
    </div>
  );
}
