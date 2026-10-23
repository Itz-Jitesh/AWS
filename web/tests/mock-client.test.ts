import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api";
import { MockApiClient } from "@/lib/mock-client";
import { DEMO_PLAN_DIGEST, DEMO_TASK_ID } from "@/lib/fixtures";

describe("MockApiClient", () => {
  let client: MockApiClient;

  beforeEach(() => {
    client = new MockApiClient();
  });

  it("creates a task without plan or approval", async () => {
    const task = await client.createTask({
      repo_source: { kind: "git_url", url: "https://github.com/example/tf.git" },
      goal: "Harden the public S3 bucket configuration.",
      mode: "build",
    });

    expect(task.state).toBe("CREATED");
    expect(task.task_id).toMatch(/^task-/);

    const workspace = await client.getWorkspace(task.task_id);
    expect(workspace.checks).toHaveLength(0);
    expect(workspace.plan_summary).toBeNull();
    expect(workspace.approval).toBeNull();
  });

  it("reports unknown tasks as not found instead of empty success", async () => {
    await expect(client.getWorkspace("missing-task")).rejects.toBeInstanceOf(ApiError);
    await expect(client.getWorkspace("missing-task")).rejects.toMatchObject({
      kind: "not_found",
    });
  });

  it("returns the demo workspace with checks, findings and a plan", async () => {
    const workspace = await client.getWorkspace(DEMO_TASK_ID);

    expect(workspace.task.state).toBe("AWAITING_APPROVAL");
    expect(workspace.checks.length).toBeGreaterThan(0);
    expect(workspace.plan_summary?.destroy).toBe(1);
    expect(workspace.findings.some((finding) => finding.status === "Failed")).toBe(
      false,
    );
    expect(
      workspace.findings.some(
        (finding) => finding.status === "UnableToVerify",
      ),
    ).toBe(true);
  });

  it("never returns NotConfigured or UnableToVerify checks as Passed", async () => {
    const { checks } = await client.runCheckSuite(DEMO_TASK_ID);

    const customPack = checks.find((check) => check.check_id === "opa-custom-pack");
    expect(customPack?.status).toBe("NotConfigured");
    expect(checks.filter((check) => check.status === "Passed").length).toBeGreaterThan(0);
    expect(
      checks.some(
        (check) =>
          check.check_id === "opa-custom-pack" && check.status === "Passed",
      ),
    ).toBe(false);
  });

  it("rejects approval when there is no plan", async () => {
    const task = await client.createTask({
      repo_source: { kind: "zip", filename: "repo.zip" },
      goal: "Inspect the networking configuration.",
      mode: "audit",
    });

    await expect(client.approveTask(task.task_id, "a".repeat(64))).rejects.toMatchObject(
      { kind: "not_found" },
    );
  });

  it("rejects approval when the plan digest differs", async () => {
    await expect(
      client.approveTask(DEMO_TASK_ID, "b".repeat(64)),
    ).rejects.toMatchObject({ kind: "invalid_response" });

    const workspace = await client.getWorkspace(DEMO_TASK_ID);
    expect(workspace.approval).toBeNull();
  });

  it("records approval for the exact captured digest", async () => {
    const response = await client.approveTask(DEMO_TASK_ID, DEMO_PLAN_DIGEST);

    expect(response.approved_plan_digest).toBe(DEMO_PLAN_DIGEST);

    const workspace = await client.getWorkspace(DEMO_TASK_ID);
    expect(workspace.approval?.approved_plan_digest).toBe(DEMO_PLAN_DIGEST);

    await expect(
      client.approveTask(DEMO_TASK_ID, "c".repeat(64)),
    ).rejects.toMatchObject({ kind: "invalid_response" });
  });

  it("builds an evidence report that discloses limitations", async () => {
    const report = await client.getEvidenceReport(DEMO_TASK_ID);

    expect(report.task_id).toBe(DEMO_TASK_ID);
    expect(report.tool_versions).toHaveProperty("terraform fmt -check", "1.9.8");
    expect(report.plan_summary?.plan_digest).toBe(DEMO_PLAN_DIGEST);
    expect(report.limitations.some((item) => /not a security guarantee/i.test(item))).toBe(
      true,
    );
    expect(report.limitations.some((item) => /Unverified/.test(item))).toBe(true);
  });
});
