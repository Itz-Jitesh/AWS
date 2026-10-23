import type { EvidenceReport, Operation, PlanProofApi, TaskWorkspace } from "./api";
import type { CheckRun } from "./contracts";

export function collectLimitations(workspace: TaskWorkspace): string[] {
  const limitations = new Set<string>();

  for (const check of workspace.checks) {
    for (const item of check.limitations ?? []) limitations.add(item);
    if (check.status === "NotConfigured") {
      limitations.add(`${check.tool} was not configured and did not evaluate anything.`);
    }
    if (check.status === "UnableToVerify") {
      limitations.add(`${check.tool} could not be verified and must not be read as passing.`);
    }
  }

  const unverified = workspace.requirements.filter(
    (requirement) => requirement.status === "Unverified",
  );
  if (unverified.length > 0) {
    limitations.add(
      `${unverified.length} requirement(s) remain Unverified and are not claimed as met.`,
    );
  }

  const unverifiable = workspace.findings.filter(
    (finding) => finding.status === "UnableToVerify",
  );
  if (unverifiable.length > 0) {
    limitations.add(
      `${unverifiable.length} finding(s) could not be verified by any scanner.`,
    );
  }

  if (!workspace.plan_summary) {
    if (workspace.plan_capture?.available) {
      limitations.add(
        "A plan digest was captured, but plan classification is unavailable, so change counts and destructive actions are unknown.",
      );
    } else {
      limitations.add("No plan JSON was captured, so no plan digest is available.");
    }
  }

  limitations.add(
    "This report records observed check results. It is not a security guarantee.",
  );

  return Array.from(limitations);
}

const BACKEND_LIMITATION: Record<PlanProofApi["backend"], string> = {
  mock: "Backend is the built-in mock service: all values are demonstration data, not live tool output.",
  "worker-direct":
    "Direct worker mode: task state is cached in this browser session; the server-side task read model does not exist yet (DEC-07).",
  orchestration:
    "Orchestration mode: endpoints follow the proposed contract and are not yet verified against a live implementation.",
};

export function collectIntegrationLimitations(api: PlanProofApi): string[] {
  const limitations = new Set<string>([BACKEND_LIMITATION[api.backend]]);
  const notes = api.operationNotes?.() ?? {};
  for (const operation of Object.keys(api.support) as Operation[]) {
    if (api.support[operation] === "unavailable") {
      limitations.add(
        `${operation}: ${notes[operation]?.detail ?? "not available in this backend"}`,
      );
    }
  }
  return Array.from(limitations);
}

export function collectToolVersions(
  checks: CheckRun[],
): Record<string, string | null> {
  const versions: Record<string, string | null> = {};
  for (const check of checks) {
    versions[check.tool] = check.tool_version ?? null;
  }
  return versions;
}

export function buildEvidenceReport(
  workspace: TaskWorkspace,
  generatedAt: string = new Date().toISOString(),
): EvidenceReport {
  return {
    task_id: workspace.task.task_id,
    generated_at: generatedAt,
    tool_versions: collectToolVersions(workspace.checks),
    checks: workspace.checks,
    findings: workspace.findings,
    requirements: workspace.requirements,
    plan_summary: workspace.plan_summary,
    limitations: collectLimitations(workspace),
  };
}
