import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { TaskWorkspace } from "@/components/TaskWorkspace";
import { setApiClient } from "@/lib/client";
import { MockApiClient } from "@/lib/mock-client";
import { DEMO_PLAN_DIGEST, DEMO_TASK_ID } from "@/lib/fixtures";

describe("TaskWorkspace", () => {
  beforeEach(() => {
    setApiClient(new MockApiClient());
  });

  it("renders the full demo workspace with a destructive plan", async () => {
    render(<TaskWorkspace taskId={DEMO_TASK_ID} />);

    expect(await screen.findByTestId("task-workspace")).toBeInTheDocument();

    expect(screen.getByTestId("task-state")).toHaveTextContent("Awaiting approval");
    expect(screen.getByTestId("banner-destructive")).toHaveTextContent(
      "aws_s3_bucket_acl.app",
    );
    expect(screen.getByTestId("plan-count-destroy")).toHaveTextContent("1");
    expect(screen.getByTestId("destroy-banner")).toBeInTheDocument();
    expect(screen.getByTestId("approval-digest")).toHaveTextContent(DEMO_PLAN_DIGEST);
    expect(screen.getByTestId("requirements-panel")).toBeInTheDocument();
    expect(screen.getByTestId("findings-list")).toBeInTheDocument();
    expect(screen.getByTestId("diff-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();
    expect(screen.getByTestId("check-run-list")).toHaveTextContent("Not configured");
  });

  it("never displays a Secure verdict or an apply action", async () => {
    render(<TaskWorkspace taskId={DEMO_TASK_ID} />);

    await screen.findByTestId("task-workspace");

    expect(screen.queryByText(/secure/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply/i })).not.toBeInTheDocument();
  });

  it("approves the exact plan digest", async () => {
    const user = userEvent.setup();
    render(<TaskWorkspace taskId={DEMO_TASK_ID} />);

    await screen.findByTestId("task-workspace");
    await user.click(screen.getByTestId("approve-button"));

    await waitFor(() =>
      expect(screen.getByTestId("approved-digest")).toHaveTextContent(DEMO_PLAN_DIGEST),
    );
    expect(screen.queryByTestId("approve-button")).not.toBeInTheDocument();
  });

  it("disables approval on a task without a captured plan", async () => {
    const client = new MockApiClient();
    setApiClient(client);
    const task = await client.createTask({
      repo_source: { kind: "git_url", url: "https://github.com/example/net.git" },
      goal: "Review the network layout before release.",
      mode: "audit",
    });

    render(<TaskWorkspace taskId={task.task_id} />);

    expect(await screen.findByTestId("task-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("missing-digest")).toBeInTheDocument();
    expect(screen.getByTestId("approve-button")).toBeDisabled();
    expect(screen.getByTestId("check-run-list")).toHaveTextContent(
      "No check suite has run for this task.",
    );
  });

  it("shows a not-found state for unknown tasks", async () => {
    render(<TaskWorkspace taskId="does-not-exist" />);

    expect(await screen.findByTestId("workspace-error")).toBeInTheDocument();
    expect(screen.getByText("Task not found")).toBeInTheDocument();
  });
});
