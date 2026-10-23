import type { EvidenceReport, TaskWorkspace } from "./api";
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
    limitations.add("No plan JSON was captured, so no plan digest is available.");
  }

  limitations.add(
    "This report records observed check results. It is not a security guarantee.",
  );

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
