import type { PlanProofApi } from "./api";
import { DirectServiceClient } from "./direct-client";
import { HttpApiClient } from "./http-client";
import { MockApiClient } from "./mock-client";
import { OrchestrationClient } from "./orchestration-client";

let client: PlanProofApi | null = null;

export function resolveApiClient(): PlanProofApi {
  const backend = process.env.NEXT_PUBLIC_BACKEND;

  if (backend === "mock") return new MockApiClient();

  // Direct mode always fetches through the same-origin /service/* proxies
  // (next.config.ts rewrites) because the worker and ai services send no CORS
  // headers. NEXT_PUBLIC_WORKER_URL / NEXT_PUBLIC_AI_URL provide proxy targets.
  if (backend === "direct" || process.env.NEXT_PUBLIC_WORKER_URL) {
    return new DirectServiceClient({
      workerUrl: "/service/worker",
      aiUrl: process.env.NEXT_PUBLIC_AI_URL ? "/service/ai" : undefined,
    });
  }

  // Legacy explicit orchestrator URL (pre-consolidation Agent A client).
  if (process.env.NEXT_PUBLIC_API_BASE_URL) {
    return new HttpApiClient(process.env.NEXT_PUBLIC_API_BASE_URL);
  }

  return new OrchestrationClient();
}

export function getApiClient(): PlanProofApi {
  if (client) return client;
  client = resolveApiClient();
  return client;
}

export function setApiClient(next: PlanProofApi | null): void {
  client = next;
}
