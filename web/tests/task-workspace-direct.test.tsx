import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { TaskWorkspace } from "@/components/TaskWorkspace";
import { setApiClient } from "@/lib/client";
import { DirectServiceClient } from "@/lib/direct-client";

const TASK_ID = "0123456789abcdef0123456789abcdef";

function json(res: ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(payload));
}

function run(status: string, checkId: string, tool: string): Record<string, unknown> {
  return {
    schema_version: "1.0.0",
    check_id: checkId,
    tool,
    status,
    started_at: "2026-10-23T10:00:00Z",
    duration_ms: 42,
    summary: `${tool}: ${status}`,
    limitations: status === "UnableToVerify" ? [`${tool} binary not found`] : [],
  };
}

describe("TaskWorkspace in direct worker mode", () => {
  let server: Server;
  let baseUrl: string;
  let checkStatus = "UnableToVerify";

  beforeEach(async () => {
    window.sessionStorage.clear();
    checkStatus = "UnableToVerify";
    server = createServer((req: IncomingMessage, res: ServerResponse) => {
      req.resume();
      req.on("end", () => {
        if (req.url === "/ingest") {
          json(res, 200, {
            task_id: TASK_ID,
            source_type: "git_url",
            tf_files: [{ path: "main.tf", size_bytes: 120 }],
            providers: [{ name: "aws" }],
            warnings: [],
          });
        } else if (req.url === "/check") {
          json(res, 200, {
            task_id: TASK_ID,
            runs: [
              run(checkStatus, "tf-fmt", "terraform fmt"),
              run(checkStatus, "tf-init", "terraform init"),
              run(checkStatus, "tf-validate", "terraform validate"),
              run(checkStatus, "tf-plan", "terraform plan"),
              run(checkStatus, "tf-show-json", "terraform show -json"),
            ],
          });
        } else if (req.url === "/capture") {
          json(res, 200, {
            available: false,
            reason: "No plan output was captured for this task.",
          });
        } else {
          json(res, 404, { code: "NOT_FOUND", message: "no route" });
        }
      });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;

    const client = new DirectServiceClient({ workerUrl: baseUrl });
    setApiClient(client);
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });
  });

  afterEach(async () => {
    setApiClient(null);
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  it("surfaces live service limits and runs the real check suite", async () => {
    const user = userEvent.setup();
    render(<TaskWorkspace taskId={TASK_ID} />);

    await screen.findByTestId("task-workspace");

    const notice = await screen.findByTestId("service-notice");
    expect(notice).toHaveTextContent(/Live worker service \(direct\)/);
    expect(notice).toHaveTextContent(/Patch generation \(unavailable\)/);
    expect(notice).toHaveTextContent(/Approval \(unavailable\)/);
    expect(notice).toHaveTextContent(/Findings \(unavailable\)/);

    expect(screen.getByTestId("state-derived-note")).toHaveTextContent("client-derived");
    expect(screen.getByTestId("ingest-summary")).toHaveTextContent("1 .tf file(s)");
    expect(screen.getByTestId("generate-patch")).toBeDisabled();
    expect(screen.queryByTestId("download-report")).not.toBeInTheDocument();
    expect(screen.getByTestId("report-unavailable")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /extract requirements/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("capture-plan")).toBeInTheDocument();

    const approvalNotice = await screen.findByTestId("approval-unavailable");
    expect(approvalNotice).toHaveTextContent(/not implemented/i);
    expect(screen.getByTestId("approve-button")).toBeDisabled();

    await user.click(screen.getByTestId("run-checks"));

    await waitFor(() =>
      expect(screen.getAllByTestId(/^check-tf-/).length).toBeGreaterThan(0),
    );
    expect(screen.getByText(/client-derived/)).toBeInTheDocument();
    expect(screen.getByTestId("banner-unverified-checks")).toHaveTextContent(
      /could not be verified or was not configured/i,
    );

    const limitations = screen.getByTestId("evidence-panel");
    expect(limitations).toHaveTextContent(/Direct worker mode/);
    expect(limitations).toHaveTextContent(/not a security guarantee/i);
  });
});
