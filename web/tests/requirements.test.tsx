import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RequirementsPanel } from "@/components/RequirementsPanel";
import { demoRequirements } from "@/lib/fixtures";
import type { Requirement } from "@/lib/contracts";

describe("RequirementsPanel", () => {
  it("renders status, mandatory tag and evidence for each requirement", () => {
    render(<RequirementsPanel requirements={demoRequirements} />);

    const retained = screen.getByTestId("requirement-r-bucket-retained");
    expect(retained).toHaveTextContent("Satisfied");
    expect(retained).toHaveTextContent("Mandatory");
    expect(retained).toHaveTextContent("PlanSummary destructive_actions");

    const unrelated = screen.getByTestId("requirement-r-no-unrelated-changes");
    expect(unrelated).toHaveTextContent("Unverified");
    expect(unrelated).toHaveTextContent("Optional");
    expect(screen.getByText(/1 unverified/)).toBeInTheDocument();
  });

  it("never claims a requirement without evidence is met", () => {
    const withoutEvidence: Requirement = {
      schema_version: "1.0.0",
      requirement_id: "r-no-evidence",
      text: "The bucket must keep versioning enabled.",
      mandatory: true,
      status: "Satisfied",
      evidence: [],
    };

    render(<RequirementsPanel requirements={[withoutEvidence]} />);

    expect(
      screen.getByText(/No evidence recorded — this requirement cannot be considered met/i),
    ).toBeInTheDocument();
  });

  it("highlights violated requirements", () => {
    const violated: Requirement = {
      schema_version: "1.0.0",
      requirement_id: "r-violated",
      text: "The database must not be replaced.",
      mandatory: true,
      status: "Violated",
      evidence: ["PlanSummary replace=1 for aws_db_instance.main."],
    };

    render(<RequirementsPanel requirements={[violated]} />);

    expect(screen.getByTestId("requirement-r-violated")).toHaveTextContent("Violated");
    expect(screen.getByText(/1 violated/)).toBeInTheDocument();
  });

  it("renders an empty state before requirements exist", () => {
    render(<RequirementsPanel requirements={[]} />);
    expect(screen.getByText("No requirements extracted yet.")).toBeInTheDocument();
  });
});
