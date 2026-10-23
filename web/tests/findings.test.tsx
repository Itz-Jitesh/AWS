import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FindingsList } from "@/components/FindingsList";
import { baselineFindings, currentFindings } from "@/lib/fixtures";

describe("FindingsList", () => {
  it("renders findings with severity, status and evidence", () => {
    render(<FindingsList findings={currentFindings} />);

    const finding = screen.getByTestId("finding-c-s3-acl");
    expect(finding).toHaveTextContent("Critical");
    expect(finding).toHaveTextContent("Passed");
    expect(finding).toHaveTextContent("CKV_AWS_21");
    expect(finding).toHaveTextContent("Evidence");
    expect(finding).toHaveTextContent("aws_s3_public_access_block.app");
  });

  it("shows unverified findings as unable to verify instead of passed", () => {
    render(<FindingsList findings={currentFindings} />);

    const unverified = screen.getByTestId("finding-c-custom-review");
    expect(unverified).toHaveTextContent("Unable to verify");
    expect(unverified).toHaveTextContent("was never evaluated");
  });

  it("sorts failing findings first", () => {
    render(<FindingsList findings={baselineFindings} />);

    const list = screen.getByTestId("findings-list");
    const firstFinding = list.querySelector("article");
    expect(firstFinding).toHaveAttribute(
      "data-testid",
      "finding-f-s3-acl",
    );
  });

  it("switches to the baseline snapshot", async () => {
    const user = userEvent.setup();
    render(<FindingsList findings={currentFindings} baseline={baselineFindings} />);

    expect(screen.queryByTestId("finding-f-s3-acl")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Baseline (before patch)" }));

    expect(screen.getByTestId("finding-f-s3-acl")).toHaveTextContent("Failed");
    expect(screen.queryByTestId("finding-c-s3-acl")).not.toBeInTheDocument();
  });

  it("renders an empty state when there are no findings", () => {
    render(<FindingsList findings={[]} />);

    expect(screen.getByText("No findings recorded for this task yet.")).toBeInTheDocument();
  });
});
