"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, type TaskWorkspace as Workspace } from "@/lib/api";
import { getApiClient } from "@/lib/client";
import {
  collectIntegrationLimitations,
  collectLimitations,
  collectToolVersions,
} from "@/lib/report";
import { isBlockingStatus } from "@/lib/ui";
import { ApprovalPanel } from "./ApprovalPanel";
import { Banner, EmptyState, Panel } from "./Panel";
import { CheckRunList } from "./CheckRunList";
import { EvidencePanel } from "./EvidencePanel";
import { FindingsList } from "./FindingsList";
import { PatchPanel } from "./PatchPanel";
import { PlanSummaryPanel } from "./PlanSummaryPanel";
import { RequirementsPanel } from "./RequirementsPanel";
import { ServiceNotice } from "./ServiceNotice";
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

function actionMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function TaskWorkspace({ taskId }: { taskId: string }) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [busy, setBusy] = useState<
    "checks" | "patch" | "requirements" | "capture" | "apply" | null
  >(null);
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
      setActionError(actionMessage(error, "The check suite failed to run."));
    } finally {
      setBusy(null);
    }
  }

  async function generatePatch() {
    const api = getApiClient();
    if (!api.generatePatch) return;
    setActionError(null);
    setBusy("patch");
    try {
      await api.generatePatch(taskId);
      await refresh();
    } catch (error) {
      setActionError(actionMessage(error, "Patch generation failed."));
    } finally {
      setBusy(null);
    }
  }

  async function extractRequirements() {
    const api = getApiClient();
    if (!api.extractRequirements) return;
    const goal = state.kind === "ready" ? state.workspace.task.goal : "";
    setActionError(null);
    setBusy("requirements");
    try {
      await api.extractRequirements(taskId, goal);
      await refresh();
    } catch (error) {
      setActionError(actionMessage(error, "Requirements extraction failed."));
    } finally {
      setBusy(null);
    }
  }

  async function capturePlan() {
    const api = getApiClient();
    if (!api.capturePlan) return;
    setActionError(null);
    setBusy("capture");
    try {
      await api.capturePlan(taskId);
      await refresh();
    } catch (error) {
      setActionError(actionMessage(error, "Plan capture failed."));
    } finally {
      setBusy(null);
    }
  }

  async function approve(digest: string) {
    await getApiClient().approveTask(taskId, digest);
    await refresh();
  }

  async function applyPatch() {
    const api = getApiClient();
    if (!api.applyPatch) return;
    if (
      !window.confirm(
        "Apply this patch to the local task workspace? The workspace files will change and checks must be re-run.",
      )
    ) {
      return;
    }
    setActionError(null);
    setBusy("apply");
    try {
      await api.applyPatch(taskId);
      await refresh();
    } catch (error) {
      setActionError(actionMessage(error, "Patch application failed."));
    } finally {
      setBusy(null);
    }
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
  const api = getApiClient();
  const support = api.support;
  const notes = api.operationNotes?.() ?? {};
  const patchUnavailable =
    support.generatePatch === "unavailable"
      ? (notes.generatePatch?.detail ??
        "Patch generation is unavailable in this backend.")
      : undefined;
  const findingsUnavailable =
    support.findings === "unavailable"
      ? (notes.findings?.detail ?? "Findings are unavailable in this backend.")
      : undefined;
  const planUnavailable =
    support.planSummary === "unavailable"
      ? (notes.planSummary?.detail ?? "Plan classification is unavailable in this backend.")
      : undefined;
  const approvalUnavailable =
    support.approveTask === "unavailable"
      ? (notes.approveTask?.detail ?? "Approval is unavailable in this backend.")
      : undefined;
  const reportUnavailable =
    support.getEvidenceReport === "unavailable"
      ? (notes.getEvidenceReport?.detail ?? "The evidence report endpoint is unavailable.")
      : undefined;

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
          {api.backend === "worker-direct" ? (
            <span
              data-testid="state-derived-note"
              className="rounded border border-line px-1.5 py-0.5 text-[11px] text-ink-dim"
              title="Server-side task states arrive with the orchestration task read model (DEC-04 pending)."
            >
              client-derived
            </span>
          ) : null}
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
              disabled={
                busy !== null ||
                task.mode === "audit" ||
                support.generatePatch === "unavailable" ||
                !api.generatePatch
              }
              title={
                task.mode === "audit"
                  ? "Patch generation is only available in build mode."
                  : patchUnavailable
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

        {workspace.ingest ? (
          <p className="text-xs text-ink-muted" data-testid="ingest-summary">
            Ingested {workspace.ingest.tf_files.length} .tf file(s)
            {workspace.ingest.providers.length > 0
              ? ` · providers: ${workspace.ingest.providers.map((provider) => provider.name).join(", ")}`
              : ""}
            {workspace.ingest.warnings.length > 0
              ? ` · ${workspace.ingest.warnings.length} ingestion warning(s)`
              : ""}
          </p>
        ) : null}
      </header>

      <ServiceNotice api={api} />

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
            <RequirementsPanel
              requirements={workspace.requirements}
              extracting={busy === "requirements"}
              unavailableReason={
                support.extractRequirements === "unavailable"
                  ? (notes.extractRequirements?.detail ?? undefined)
                  : undefined
              }
              onExtract={
                support.extractRequirements === "available" && api.extractRequirements
                  ? extractRequirements
                  : undefined
              }
            />
          </Panel>

          <Panel
            title="Findings"
            description="Normalized from Checkov, OPA and custom rules."
            testId="panel-findings"
          >
            <FindingsList
              findings={workspace.findings}
              baseline={workspace.baseline_findings}
              unavailableReason={findingsUnavailable}
            />
          </Panel>
        </div>

        <div className="flex flex-col gap-5 lg:col-span-5">
          <Panel
            title="Plan summary"
            description="Classified from terraform show -json output."
            testId="panel-plan"
          >
            <PlanSummaryPanel
              planSummary={planSummary}
              capture={workspace.plan_capture}
              capturing={busy === "capture"}
              unavailableReason={planUnavailable}
              onCapture={
                support.capturePlan === "available" && api.capturePlan && !planSummary
                  ? capturePlan
                  : undefined
              }
            />
          </Panel>

          <Panel
            title="Approval"
            description="Human approval bound to the exact plan digest."
            testId="panel-approval"
          >
            <ApprovalPanel
              state={workspace.task.state}
              approvalValid={workspace.task.approval_valid}
              planSummary={planSummary}
              approval={approval}
              capture={workspace.plan_capture}
              unavailableReason={approvalUnavailable}
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
        <PatchPanel
          patch={workspace.patch}
          unavailableReason={patchUnavailable}
          appliedAt={workspace.patch_applied_at}
          applying={busy === "apply"}
          onApply={
            workspace.patch &&
            workspace.patch_applied_at == null &&
            task.mode === "build" &&
            api.applyPatch
              ? applyPatch
              : undefined
          }
        />
      </Panel>

      <Panel
        title="Evidence report"
        description="Versions, statuses, digest and limitations for this task."
        testId="panel-evidence"
      >
        <EvidencePanel
          taskId={task.task_id}
          limitations={[
            ...collectLimitations(workspace),
            ...collectIntegrationLimitations(api),
          ]}
          toolVersions={collectToolVersions(workspace.checks)}
          reportSupported={support.getEvidenceReport !== "unavailable"}
          unavailableReason={reportUnavailable}
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
