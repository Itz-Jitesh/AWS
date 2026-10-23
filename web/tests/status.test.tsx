import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  RequirementStatusBadge,
  RiskBadge,
  SeverityBadge,
  StateBadge,
  StatusBadge,
} from "@/components/badges";
import { isBlockingStatus, severityRank, statusRank } from "@/lib/ui";

describe("StatusBadge", () => {
  it("renders Passed as a success state", () => {
    render(<StatusBadge status="Passed" />);
    expect(screen.getByText("Passed")).toBeInTheDocument();
  });

  it("never renders UnableToVerify as Passed", () => {
    render(<StatusBadge status="UnableToVerify" />);
    expect(screen.getByText("Unable to verify")).toBeInTheDocument();
    expect(screen.queryByText("Passed")).not.toBeInTheDocument();
  });

  it("renders NotConfigured distinctly from Passed", () => {
    render(<StatusBadge status="NotConfigured" />);
    expect(screen.getByText("Not configured")).toBeInTheDocument();
    expect(screen.queryByText("Passed")).not.toBeInTheDocument();
  });

  it("renders Failed", () => {
    render(<StatusBadge status="Failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("badges", () => {
  it("maps severity labels", () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
  });

  it("maps requirement statuses", () => {
    render(<RequirementStatusBadge status="Unverified" />);
    expect(screen.getByText("Unverified")).toBeInTheDocument();
  });

  it("renders risk level", () => {
    render(<RiskBadge risk="high" />);
    expect(screen.getByText("HIGH RISK")).toBeInTheDocument();
  });

  it("renders the task state label", () => {
    render(<StateBadge state="AWAITING_APPROVAL" />);
    expect(screen.getByTestId("task-state")).toHaveTextContent("Awaiting approval");
  });
});

describe("status helpers", () => {
  it("treats failure and inability to verify as blocking", () => {
    expect(isBlockingStatus("Failed")).toBe(true);
    expect(isBlockingStatus("UnableToVerify")).toBe(true);
    expect(isBlockingStatus("NotConfigured")).toBe(false);
    expect(isBlockingStatus("Passed")).toBe(false);
  });

  it("ranks unresolved statuses before passing ones", () => {
    expect(statusRank("Failed")).toBeLessThan(statusRank("UnableToVerify"));
    expect(statusRank("UnableToVerify")).toBeLessThan(statusRank("Passed"));
  });

  it("ranks critical severity first", () => {
    expect(severityRank("critical")).toBeLessThan(severityRank("high"));
    expect(severityRank("unknown")).toBeGreaterThan(severityRank("info"));
  });
});
