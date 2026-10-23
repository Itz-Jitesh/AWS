import type { PlanProofApi } from "./api";
import { DirectServiceClient } from "./direct-client";
import { HttpApiClient } from "./http-client";
import { MockApiClient } from "./mock-client";

let client: PlanProofApi | null = null;

export function resolveApiClient(): PlanProofApi {
  const orchestrationUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (orchestrationUrl) return new HttpApiClient(orchestrationUrl);

  // Direct mode always fetches through the same-origin /service/* proxies
  // (next.config.ts rewrites) because the worker and ai services send no CORS
  // headers. NEXT_PUBLIC_WORKER_URL / NEXT_PUBLIC_AI_URL enable the mode and
  // provide the server-side proxy targets.
  const workerEnabled = Boolean(process.env.NEXT_PUBLIC_WORKER_URL);
  if (workerEnabled) {
    return new DirectServiceClient({
      workerUrl: "/service/worker",
      aiUrl: process.env.NEXT_PUBLIC_AI_URL ? "/service/ai" : undefined,
    });
  }

  return new MockApiClient();
}

export function getApiClient(): PlanProofApi {
  if (client) return client;
  client = resolveApiClient();
  return client;
}

export function setApiClient(next: PlanProofApi | null): void {
  client = next;
}
