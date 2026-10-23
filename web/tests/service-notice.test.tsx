import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { PlanProofApi, SupportMap } from "@/lib/api";
import { ServiceNotice } from "@/components/ServiceNotice";

function fakeApi(overrides: {
  backend?: PlanProofApi["backend"];
  support?: Partial<SupportMap>;
  notes?: Partial<Record<string, { level: "available" | "unverified" | "unavailable"; detail: string }>>;
}): PlanProofApi {
  const support: SupportMap = {
    createTask: "available",
    getWorkspace: "available",
    runCheckSuite: "available",
    findings: "unavailable",
    extractRequirements: "unavailable",
    generatePatch: "unavailable",
    planSummary: "unavailable",
    capturePlan: "available",
    approveTask: "unavailable",
    getEvidenceReport: "unavailable",
    ...overrides.support,
  };
  return {
    backend: overrides.backend ?? "worker-direct",
    support,
    createTask: () => Promise.reject(new Error("not used")),
    getWorkspace: () => Promise.reject(new Error("not used")),
    runCheckSuite: () => Promise.reject(new Error("not used")),
    approveTask: () => Promise.reject(new Error("not used")),
    getEvidenceReport: () => Promise.reject(new Error("not used")),
    operationNotes: () => overrides.notes ?? {},
  };
}

describe("ServiceNotice", () => {
  it("lists blocked and unverified operations for a live backend", () => {
    render(
      <ServiceNotice
        api={fakeApi({
          notes: {
            findings: {
              level: "unavailable",
              detail: "The audit service exposes no HTTP findings endpoint.",
            },
            approveTask: {
              level: "unavailable",
              detail: "POST /tasks/{id}/approve is not implemented. Owner: Agent B.",
            },
            runCheckSuite: {
              level: "available",
              detail: "POST /check on the worker service.",
            },
          },
        })}
      />,
    );

    const notice = screen.getByTestId("service-notice");
    expect(notice).toBeInTheDocument();
    expect(notice).toHaveTextContent(/Live worker service \(direct\)/);
    expect(notice).toHaveTextContent(/Findings \(unavailable\)/);
    expect(notice).toHaveTextContent(/Approval \(unavailable\)/);
    expect(notice).toHaveTextContent(/no HTTP findings endpoint/);
    expect(notice).not.toHaveTextContent(/Check suite/);
    expect(notice).toHaveTextContent(/demonstration data is never substituted/i);
  });

  it("renders nothing when every operation is available", () => {
    const { container } = render(
      <ServiceNotice
        api={fakeApi({
          backend: "mock",
          support: {
            findings: "available",
            extractRequirements: "available",
            generatePatch: "available",
            planSummary: "available",
            approveTask: "available",
            getEvidenceReport: "available",
          },
        })}
      />,
    );
    expect(screen.queryByTestId("service-notice")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });
});
