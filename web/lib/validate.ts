import type { CheckRun, Finding, PlanSummary, Requirement } from "./contracts";

const CHECK_STATUSES = new Set([
  "Passed",
  "Failed",
  "Skipped",
  "NotConfigured",
  "UnableToVerify",
]);

const SEVERITIES = new Set(["critical", "high", "medium", "low", "info", "unknown"]);

const REQUIREMENT_STATUSES = new Set(["Satisfied", "Unverified", "Violated"]);

export const DIGEST_PATTERN = /^[a-f0-9]{64}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isCheckRun(value: unknown): value is CheckRun {
  if (!isRecord(value)) return false;
  return (
    value.schema_version === "1.0.0" &&
    typeof value.check_id === "string" &&
    value.check_id.length > 0 &&
    typeof value.tool === "string" &&
    value.tool.length > 0 &&
    typeof value.status === "string" &&
    CHECK_STATUSES.has(value.status) &&
    typeof value.started_at === "string" &&
    typeof value.duration_ms === "number" &&
    value.duration_ms >= 0 &&
    typeof value.summary === "string"
  );
}

export function isCheckRunList(value: unknown): value is CheckRun[] {
  return Array.isArray(value) && value.length > 0 && value.every(isCheckRun);
}

export function isRequirement(value: unknown): value is Requirement {
  if (!isRecord(value)) return false;
  return (
    value.schema_version === "1.0.0" &&
    typeof value.requirement_id === "string" &&
    value.requirement_id.length > 0 &&
    typeof value.text === "string" &&
    value.text.length > 0 &&
    typeof value.mandatory === "boolean" &&
    typeof value.status === "string" &&
    REQUIREMENT_STATUSES.has(value.status)
  );
}

export function isRequirementList(value: unknown): value is Requirement[] {
  return Array.isArray(value) && value.every(isRequirement);
}

export function isFinding(value: unknown): value is Finding {
  if (!isRecord(value)) return false;
  return (
    value.schema_version === "1.0.0" &&
    typeof value.finding_id === "string" &&
    value.finding_id.length > 0 &&
    typeof value.rule_source === "string" &&
    typeof value.rule_id === "string" &&
    typeof value.severity === "string" &&
    SEVERITIES.has(value.severity) &&
    typeof value.status === "string" &&
    CHECK_STATUSES.has(value.status) &&
    typeof value.title === "string" &&
    typeof value.evidence === "string" &&
    value.evidence.length > 0
  );
}

export function isPlanSummary(value: unknown): value is PlanSummary {
  if (!isRecord(value)) return false;
  if (typeof value.plan_digest !== "string" || !DIGEST_PATTERN.test(value.plan_digest)) {
    return false;
  }
  const counts = ["create", "update", "replace", "destroy"];
  if (!counts.every((key) => typeof value[key] === "number" && (value[key] as number) >= 0)) {
    return false;
  }
  return (
    value.schema_version === "1.0.0" &&
    Array.isArray(value.destructive_actions) &&
    typeof value.has_changes === "boolean"
  );
}

export function isRecordId(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}
