import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApprovalPanel } from "@/components/ApprovalPanel";
import { DEMO_PLAN_DIGEST, demoWorkspace } from "@/lib/fixtures";

const AWAITING = demoWorkspace.task.state;

describe("ApprovalPanel", () => {
  it("disables approval when the plan digest is missing", () => {
    const onApprove = vi.fn();

    render(
      <ApprovalPanel
        state={AWAITING}
        planSummary={null}
        approval={null}
        onApprove={onApprove}
      />,
    );

    expect(screen.getByTestId("missing-digest")).toBeInTheDocument();
    expect(screen.getByTestId("approve-button")).toBeDisabled();
    expect(screen.queryByTestId("approval-digest")).not.toBeInTheDocument();
  });

  it("disables approval when the plan digest is malformed", () => {
    const onApprove = vi.fn();
    const malformed = {
      ...demoWorkspace.plan_summary!,
      plan_digest: "not-a-sha256",
    };

    render(
      <ApprovalPanel
        state={AWAITING}
        planSummary={malformed}
        approval={null}
        onApprove={onApprove}
      />,
    );

    expect(screen.getByTestId("approve-button")).toBeDisabled();
    expect(screen.getByTestId("approval-digest")).toHaveTextContent(
      "not-a-sha256",
    );
    expect(screen.getByText(/not a valid sha256/i)).toBeInTheDocument();
    expect(onApprove).not.toHaveBeenCalled();
  });

  it("disables approval when the task state is not awaiting approval", () => {
    const onApprove = vi.fn();

    render(
      <ApprovalPanel
        state="REVIEW_READY"
        planSummary={demoWorkspace.plan_summary}
        approval={null}
        onApprove={onApprove}
      />,
    );

    expect(screen.getByTestId("approve-button")).toBeDisabled();
    expect(
      screen.getByText(/only opens when the task state is awaiting approval/i),
    ).toBeInTheDocument();
    expect(onApprove).not.toHaveBeenCalled();
  });

  it("disables approval when the server marks approval_valid as false", () => {
    const onApprove = vi.fn();

    render(
      <ApprovalPanel
        state={AWAITING}
        approvalValid={false}
        planSummary={demoWorkspace.plan_summary}
        approval={null}
        onApprove={onApprove}
      />,
    );

    expect(screen.getByTestId("approve-button")).toBeDisabled();
    expect(
      screen.getByText(/server marked this task's approval as invalid/i),
    ).toBeInTheDocument();
    expect(onApprove).not.toHaveBeenCalled();
  });

  it("shows the digest and approves exactly that value", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn().mockResolvedValue(undefined);

    render(
      <ApprovalPanel
        state={AWAITING}
        planSummary={demoWorkspace.plan_summary}
        approval={null}
        onApprove={onApprove}
      />,
    );

    expect(screen.getByTestId("approval-digest")).toHaveTextContent(
      DEMO_PLAN_DIGEST,
    );
    expect(screen.getByTestId("approve-button")).toBeEnabled();

    await user.click(screen.getByTestId("approve-button"));

    await waitFor(() => expect(onApprove).toHaveBeenCalledWith(DEMO_PLAN_DIGEST));
  });

  it("surfaces a rejected approval without recording consent", async () => {
    const user = userEvent.setup();
    const onApprove = vi
      .fn()
      .mockRejectedValue(
        new Error("The plan digest no longer matches the captured plan."),
      );

    render(
      <ApprovalPanel
        state={AWAITING}
        planSummary={demoWorkspace.plan_summary}
        approval={null}
        onApprove={onApprove}
      />,
    );

    await user.click(screen.getByTestId("approve-button"));

    expect(await screen.findByTestId("approval-error")).toHaveTextContent(
      "The plan digest no longer matches the captured plan.",
    );
    expect(screen.queryByTestId("approved-digest")).not.toBeInTheDocument();
    expect(screen.getByTestId("approve-button")).toBeEnabled();
  });

  it("lists destructive actions before consent", () => {
    render(
      <ApprovalPanel
        state={AWAITING}
        planSummary={demoWorkspace.plan_summary}
        approval={null}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.getByText("Review destructive actions first")).toBeInTheDocument();
    expect(screen.getByText(/aws_s3_bucket_acl\.app/)).toBeInTheDocument();
  });

  it("shows a recorded approval and hides the approve button", () => {
    render(
      <ApprovalPanel
        state={AWAITING}
        planSummary={demoWorkspace.plan_summary}
        approval={{
          approved_plan_digest: DEMO_PLAN_DIGEST,
          approved_at: "2026-10-23T10:30:00.000Z",
        }}
        onApprove={vi.fn()}
      />,
    );

    expect(screen.getByTestId("approved-digest")).toHaveTextContent(
      DEMO_PLAN_DIGEST,
    );
    expect(screen.queryByTestId("approve-button")).not.toBeInTheDocument();
    expect(screen.getByText(/not enabled in the MVP/i)).toBeInTheDocument();
  });
});
