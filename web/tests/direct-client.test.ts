import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import { DirectServiceClient } from "@/lib/direct-client";
import { resolveApiClient } from "@/lib/client";

type Handler = (req: IncomingMessage, res: ServerResponse, raw: string) => void;

interface Stub {
  url: string;
  close: () => Promise<void>;
  requests: Array<{ method: string; url: string; body: string; contentType: string }>;
}

const TASK_ID = "0123456789abcdef0123456789abcdef";
const DIGEST = "a".repeat(64);

async function startStub(handler: Handler): Promise<Stub> {
  const requests: Stub["requests"] = [];
  const server: Server = createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      requests.push({
        method: req.method ?? "",
        url: req.url ?? "",
        body: raw,
        contentType: String(req.headers["content-type"] ?? ""),
      });
      handler(req, res, raw);
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}`,
    requests,
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}

function json(res: ServerResponse, status: number, payload: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(payload));
}

function ingestResponse(): Record<string, unknown> {
  return {
    task_id: TASK_ID,
    source_type: "git_url",
    tf_files: [{ path: "main.tf", size_bytes: 120 }],
    providers: [{ name: "aws", source: "hashicorp/aws", version: "5.31.0" }],
    warnings: [],
  };
}

function passingRun(checkId: string, tool: string): Record<string, unknown> {
  return {
    schema_version: "1.0.0",
    check_id: checkId,
    tool,
    status: "Passed",
    started_at: "2026-10-23T10:00:00Z",
    duration_ms: 42,
    summary: `${tool} passed`,
    limitations: [],
  };
}

describe("DirectServiceClient against a local HTTP stub", () => {
  let stubs: Stub[] = [];

  async function track(handler: Handler): Promise<Stub> {
    const created = await startStub(handler);
    stubs.push(created);
    return created;
  }

  beforeEach(() => {
    stubs = [];
    window.sessionStorage.clear();
  });

  afterEach(async () => {
    vi.unstubAllGlobals();
    for (const item of stubs) await item.close();
  });

  it("ingests a git_url source and caches the workspace", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest" && req.method === "POST") {
        json(res, 200, ingestResponse());
      } else {
        json(res, 404, { code: "NOT_FOUND", message: "no route" });
      }
    });
    const client = new DirectServiceClient({ workerUrl: server.url });

    const task = await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    expect(task.task_id).toBe(TASK_ID);
    expect(task.state).toBe("CREATED");
    expect(server.requests[0]?.url).toBe("/ingest");
    expect(JSON.parse(server.requests[0]?.body ?? "{}")).toEqual({
      source_type: "git_url",
      git_url: "https://example.com/org/repo.git",
    });

    const workspace = await client.getWorkspace(TASK_ID);
    expect(workspace.ingest?.tf_files).toHaveLength(1);
    expect(workspace.ingest?.providers[0]?.name).toBe("aws");
    expect(workspace.checks).toHaveLength(0);
  });

  it("rejects a zip source when no file is attached", async () => {
    const client = new DirectServiceClient({ workerUrl: "http://127.0.0.1:1" });
    await expect(
      client.createTask({
        repo_source: { kind: "zip", filename: "repo.zip" },
        goal: "Make the bucket private without deleting it.",
        mode: "build",
      }),
    ).rejects.toMatchObject({ kind: "rejected" } satisfies Partial<ApiError>);
  });

  it("uploads a zip file as multipart form data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit) => {
        expect(url).toBe("http://stub.local/ingest/upload");
        const form = init.body as FormData;
        expect(form).toBeInstanceOf(FormData);
        const file = form.get("file") as File | null;
        expect(file?.name).toBe("repo.zip");
        return new Response(JSON.stringify(ingestResponse()), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );

    const client = new DirectServiceClient({ workerUrl: "http://stub.local" });
    const file = new File(["zip-bytes"], "repo.zip", { type: "application/zip" });
    const task = await client.createTask({
      repo_source: { kind: "zip", filename: "repo.zip", file },
      goal: "Make the bucket private without deleting it.",
      mode: "audit",
    });
    expect(task.task_id).toBe(TASK_ID);
    expect(fetch).toHaveBeenCalledWith(
      "http://stub.local/ingest/upload",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("requests the full mandatory check set and derives REVIEW_READY when all pass", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      if (req.url === "/check") {
        return json(res, 200, {
          task_id: TASK_ID,
          runs: [
            passingRun("tf-fmt", "terraform fmt"),
            passingRun("tf-init", "terraform init"),
            passingRun("tf-validate", "terraform validate"),
            passingRun("tf-plan", "terraform plan"),
            passingRun("tf-show-json", "terraform show -json"),
          ],
        });
      }
      json(res, 404, { code: "NOT_FOUND", message: "no route" });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    const suite = await client.runCheckSuite(TASK_ID);
    const checkRequest = server.requests.find((entry) => entry.url === "/check");
    expect(JSON.parse(checkRequest?.body ?? "{}")).toEqual({
      task_id: TASK_ID,
      checks: ["fmt", "init", "validate", "plan", "show_json"],
    });
    expect(suite.checks).toHaveLength(5);

    const workspace = await client.getWorkspace(TASK_ID);
    expect(workspace.task.state).toBe("REVIEW_READY");
  });

  it("derives CHECKING when a mandatory check cannot verify", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      if (req.url === "/check") {
        return json(res, 200, {
          task_id: TASK_ID,
          runs: [
            {
              ...passingRun("tf-fmt", "terraform fmt"),
              status: "UnableToVerify",
              summary: "terraform binary not found",
            },
            passingRun("tf-init", "terraform init"),
            passingRun("tf-validate", "terraform validate"),
            passingRun("tf-plan", "terraform plan"),
            passingRun("tf-show-json", "terraform show -json"),
          ],
        });
      }
      json(res, 404, { code: "NOT_FOUND", message: "no route" });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    await client.runCheckSuite(TASK_ID);
    const workspace = await client.getWorkspace(TASK_ID);
    expect(workspace.task.state).toBe("CHECKING");
    expect(
      workspace.checks.find((check) => check.check_id === "tf-fmt")?.status,
    ).toBe("UnableToVerify");
  });

  it("fails closed on an empty check suite", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      if (req.url === "/check") return json(res, 200, { task_id: TASK_ID, runs: [] });
      json(res, 404, { code: "NOT_FOUND", message: "no route" });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    await expect(client.runCheckSuite(TASK_ID)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("fails closed when a run does not match the check contract", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      if (req.url === "/check") {
        return json(res, 200, {
          task_id: TASK_ID,
          runs: [{ check_id: "tf-fmt", status: "Passed" }],
        });
      }
      json(res, 404, { code: "NOT_FOUND", message: "no route" });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    await expect(client.runCheckSuite(TASK_ID)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("maps worker error codes to typed API errors", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 404, { code: "TASK_NOT_FOUND", message: "Task not found." });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    await expect(client.runCheckSuite(TASK_ID)).rejects.toMatchObject({
      kind: "not_found",
      status: 404,
      code: "TASK_NOT_FOUND",
    });
  });

  it("surfaces structured 5xx service errors but never unstructured bodies", async () => {
    const structured = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 503, {
        detail: { code: "TOOL_UNAVAILABLE", message: "terraform is not installed" },
      });
    });
    const client = new DirectServiceClient({ workerUrl: structured.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });
    const structuredError = await client.runCheckSuite(TASK_ID).catch((c: unknown) => c);
    expect(structuredError).toBeInstanceOf(ApiError);
    expect((structuredError as ApiError).kind).toBe("network");
    expect((structuredError as ApiError).message).toContain("terraform is not installed");
    expect((structuredError as ApiError).message).toContain("TOOL_UNAVAILABLE");
    expect((structuredError as ApiError).code).toBe("TOOL_UNAVAILABLE");

    const unstructured = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      res.writeHead(500, { "content-type": "text/html" });
      res.end("<html><body>Traceback: /srv/secrets/path</body></html>");
    });
    const htmlClient = new DirectServiceClient({ workerUrl: unstructured.url });
    await htmlClient.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });
    const htmlError = await htmlClient.runCheckSuite(TASK_ID).catch((c: unknown) => c);
    expect(htmlError).toBeInstanceOf(ApiError);
    expect((htmlError as ApiError).message).toBe(
      "The service failed with HTTP 500.",
    );
    expect((htmlError as ApiError).message).not.toContain("Traceback");
    expect((htmlError as ApiError).code).toBeUndefined();
  });

  it("surfaces the code and message from 4xx detail payloads", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 422, {
        detail: { code: "CHECK_NOT_ALLOWED", message: "check is not allowed." },
      });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    await expect(client.runCheckSuite(TASK_ID)).rejects.toMatchObject({
      kind: "rejected",
      status: 422,
      code: "CHECK_NOT_ALLOWED",
      message: "check is not allowed.",
    });
  });

  it("times out when the worker does not respond", async () => {
    const server = await track(() => {
      /* never respond */
    });
    const client = new DirectServiceClient({
      workerUrl: server.url,
      timeoutMs: 120,
    });
    await expect(
      client.createTask({
        repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
        goal: "Make the bucket private without deleting it.",
        mode: "build",
      }),
    ).rejects.toMatchObject({ kind: "timeout" });
  });

  it("requires a cached session for workspace reads", async () => {
    const client = new DirectServiceClient({ workerUrl: "http://127.0.0.1:1" });
    await expect(client.getWorkspace(TASK_ID)).rejects.toMatchObject({
      kind: "not_supported",
    });
    await expect(client.getWorkspace(TASK_ID)).rejects.toThrow(/DEC-07/);
  });

  it("extracts requirements from the AI service and validates the contract", async () => {
    const ai = await track((req, res) => {
      if (req.url === `/tasks/${TASK_ID}/requirements`) {
        return json(res, 200, {
          requirements: [
            {
              schema_version: "1.0.0",
              requirement_id: "req-1",
              text: "The bucket must be private.",
              mandatory: true,
              status: "Unverified",
            },
          ],
        });
      }
      json(res, 404, { detail: "not found" });
    });
    const worker = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 404, { detail: "not found" });
    });
    const client = new DirectServiceClient({
      workerUrl: worker.url,
      aiUrl: ai.url,
    });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    const requirements = await client.extractRequirements(
      TASK_ID,
      "Make the bucket private without deleting it.",
    );
    expect(requirements).toHaveLength(1);
    const workspace = await client.getWorkspace(TASK_ID);
    expect(workspace.requirements[0]?.requirement_id).toBe("req-1");
  });

  it("reports a missing AI configuration instead of guessing", async () => {
    const worker = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 404, { detail: "not found" });
    });
    const client = new DirectServiceClient({ workerUrl: worker.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    await expect(client.extractRequirements(TASK_ID, "goal")).rejects.toMatchObject({
      kind: "not_configured",
    });
  });

  it("captures the plan digest and rejects malformed digests", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      if (req.url === "/capture") {
        return json(res, 200, {
          available: true,
          plan_digest: DIGEST,
          captured_at: "2026-10-23T10:05:00Z",
        });
      }
      json(res, 404, { detail: "not found" });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    const capture = await client.capturePlan(TASK_ID);
    expect(capture.available).toBe(true);
    expect(capture.plan_digest).toBe(DIGEST);
    const workspace = await client.getWorkspace(TASK_ID);
    expect(workspace.plan_capture?.plan_digest).toBe(DIGEST);
    expect(workspace.plan_summary).toBeNull();

    const bad = await startStub((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 200, { available: true, plan_digest: "not-a-digest" });
    });
    stubs.push(bad);
    window.sessionStorage.clear();
    const badClient = new DirectServiceClient({ workerUrl: bad.url });
    await badClient.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });
    await expect(badClient.capturePlan(TASK_ID)).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("keeps capture-unavailable responses explicit", async () => {
    const server = await track((req, res) => {
      if (req.url === "/ingest") return json(res, 200, ingestResponse());
      json(res, 200, {
        available: false,
        reason: "No plan output was captured for this task.",
      });
    });
    const client = new DirectServiceClient({ workerUrl: server.url });
    await client.createTask({
      repo_source: { kind: "git_url", url: "https://example.com/org/repo.git" },
      goal: "Make the bucket private without deleting it.",
      mode: "build",
    });

    const capture = await client.capturePlan(TASK_ID);
    expect(capture.available).toBe(false);
    expect(capture.reason).toContain("No plan output");
  });

  it("fails closed for blocked operations", async () => {
    const client = new DirectServiceClient({ workerUrl: "http://127.0.0.1:1" });
    await expect(client.generatePatch()).rejects.toMatchObject({
      kind: "not_supported",
    });
    await expect(client.approveTask()).rejects.toMatchObject({
      kind: "not_supported",
    });
    await expect(client.getEvidenceReport()).rejects.toMatchObject({
      kind: "not_supported",
    });
    expect(client.support.generatePatch).toBe("unavailable");
    expect(client.support.approveTask).toBe("unavailable");
    expect(client.support.getEvidenceReport).toBe("unavailable");
    expect(client.support.findings).toBe("unavailable");
    expect(client.support.runCheckSuite).toBe("available");
  });
});

describe("client factory precedence", () => {
  const original = {
    api: process.env.NEXT_PUBLIC_API_BASE_URL,
    worker: process.env.NEXT_PUBLIC_WORKER_URL,
    ai: process.env.NEXT_PUBLIC_AI_URL,
  };

  afterEach(() => {
    if (original.api === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = original.api;
    if (original.worker === undefined) delete process.env.NEXT_PUBLIC_WORKER_URL;
    else process.env.NEXT_PUBLIC_WORKER_URL = original.worker;
    if (original.ai === undefined) delete process.env.NEXT_PUBLIC_AI_URL;
    else process.env.NEXT_PUBLIC_AI_URL = original.ai;
  });

  it("prefers the orchestration API, then the worker, then mock", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://orchestrator.local";
    process.env.NEXT_PUBLIC_WORKER_URL = "http://worker.local";
    expect(resolveApiClient().backend).toBe("orchestration");

    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    expect(resolveApiClient().backend).toBe("worker-direct");

    delete process.env.NEXT_PUBLIC_WORKER_URL;
    expect(resolveApiClient().backend).toBe("mock");
  });
});
