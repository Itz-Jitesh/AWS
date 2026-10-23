import type { PlanProofApi } from "./api";
import { HttpApiClient } from "./http-client";
import { MockApiClient } from "./mock-client";

let client: PlanProofApi | null = null;

export function getApiClient(): PlanProofApi {
  if (client) return client;
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  client = baseUrl ? new HttpApiClient(baseUrl) : new MockApiClient();
  return client;
}

export function setApiClient(next: PlanProofApi | null): void {
  client = next;
}
