import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020";
import type { ValidateFunction } from "ajv";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";
import {
  baselineFindings,
  buildEmptyWorkspace,
  demoChecks,
  demoPatch,
  demoRequirements,
  demoWorkspace,
  currentFindings,
} from "@/lib/fixtures";
import { buildEvidenceReport } from "@/lib/report";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);

function loadSchema(name: string): object {
  return JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", name), "utf8"),
  ) as object;
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

const validateCheckRun = ajv.compile(loadSchema("checkrun.schema.json"));
const validateFinding = ajv.compile(loadSchema("finding.schema.json"));
const validateRequirement = ajv.compile(loadSchema("requirement.schema.json"));
const validatePatch = ajv.compile(loadSchema("patch.schema.json"));
const validatePlanSummary = ajv.compile(loadSchema("plan-summary.schema.json"));

function expectValid(
  validate: ValidateFunction,
  data: unknown,
  label: string,
) {
  const valid = validate(data);
  expect(valid, `${label}: ${JSON.stringify(validate.errors)}`).toBe(true);
}

describe("fixtures against frozen contracts", () => {
  it("validates every demo check run", () => {
    demoChecks.forEach((check, index) => {
      expectValid(validateCheckRun, check, `demoChecks[${index}]`);
    });
  });

  it("validates baseline and current findings", () => {
    [...baselineFindings, ...currentFindings].forEach((finding, index) => {
      expectValid(validateFinding, finding, `findings[${index}]`);
    });
  });

  it("validates extracted requirements", () => {
    demoRequirements.forEach((requirement, index) => {
      expectValid(validateRequirement, requirement, `demoRequirements[${index}]`);
    });
  });

  it("validates the proposed patch", () => {
    expectValid(validatePatch, demoPatch, "demoPatch");
  });

  it("validates the demo plan summary", () => {
    expect(demoWorkspace.plan_summary).not.toBeNull();
    expectValid(validatePlanSummary, demoWorkspace.plan_summary, "plan_summary");
  });

  it("validates a freshly created task workspace", () => {
    const empty = buildEmptyWorkspace({
      task_id: "task-9",
      state: "CREATED",
      goal: "Inspect the VPC layout.",
      mode: "audit",
      created_at: "2026-10-23T10:00:00.000Z",
    });
    expect(empty.checks).toHaveLength(0);
    expect(empty.plan_summary).toBeNull();
    expect(empty.approval).toBeNull();
  });

  it("produces an evidence report with versions, digest and limitations", () => {
    const report = buildEvidenceReport(demoWorkspace, "2026-10-23T10:20:00.000Z");

    expect(report.task_id).toBe("demo");
    expect(report.tool_versions["checkov -d ."]).toBe("3.2.333");
    expect(report.plan_summary?.plan_digest).toBe(demoWorkspace.plan_summary?.plan_digest);
    expect(report.limitations.length).toBeGreaterThan(0);
    expect(
      report.limitations.some((item) => /not a security guarantee/i.test(item)),
    ).toBe(true);
    expect(
      report.limitations.some((item) => /Unverified/.test(item)),
    ).toBe(true);
    expect(
      report.limitations.some((item) => /was not configured/.test(item)),
    ).toBe(true);
  });
});
