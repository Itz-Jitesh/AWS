import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanSummaryPanel } from "@/components/PlanSummaryPanel";
import { demoWorkspace } from "@/lib/fixtures";

describe("PlanSummaryPanel", () => {
  it("shows create, update, replace and destroy counts with a destroy banner", () => {
    render(<PlanSummaryPanel planSummary={demoWorkspace.plan_summary} />);

    expect(screen.getByTestId("plan-count-create")).toHaveTextContent("2");
    expect(screen.getByTestId("plan-count-update")).toHaveTextContent("1");
    expect(screen.getByTestId("plan-count-replace")).toHaveTextContent("0");
    expect(screen.getByTestId("plan-count-destroy")).toHaveTextContent("1");
    expect(screen.getByTestId("destroy-banner")).toBeInTheDocument();
  });

  it("lists destructive actions explicitly with risk", () => {
    render(<PlanSummaryPanel planSummary={demoWorkspace.plan_summary} />);

    const action = screen.getByTestId("destructive-aws_s3_bucket_acl.app");
    expect(action).toHaveTextContent("delete");
    expect(action).toHaveTextContent("HIGH RISK");
  });

  it("renders the full plan digest", () => {
    render(<PlanSummaryPanel planSummary={demoWorkspace.plan_summary} />);

    expect(screen.getByTestId("plan-digest")).toHaveTextContent(
      demoWorkspace.plan_summary?.plan_digest ?? "",
    );
  });

  it("explains that a missing plan blocks approval", () => {
    render(<PlanSummaryPanel planSummary={null} />);

    expect(screen.getByText("No plan captured yet.")).toBeInTheDocument();
    expect(
      screen.getByText(/digest is required before approval/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("destroy-banner")).not.toBeInTheDocument();
  });
});
