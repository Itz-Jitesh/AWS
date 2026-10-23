import { NextResponse } from "next/server";

export class UpstreamError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "UpstreamError";
    this.status = status;
    this.code = code;
  }
}

export class RequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "RequestError";
    this.status = status;
    this.code = code;
  }
}

export function errorResponse(error: unknown): NextResponse {
  if (error instanceof UpstreamError || error instanceof RequestError) {
    return NextResponse.json(
      { detail: { code: error.code, message: error.message } },
      { status: error.status },
    );
  }
  const message = error instanceof Error ? error.message : "unexpected server error";
  return NextResponse.json(
    { detail: { code: "internal_error", message } },
    { status: 500 },
  );
}

interface FetchOptions {
  timeoutMs?: number;
  method?: "GET" | "POST";
  body?: BodyInit;
  headers?: Record<string, string>;
}

export async function fetchJson<T>(
  url: string,
  options: FetchOptions = {},
): Promise<T> {
  const { timeoutMs = 30_000, method = "GET", body, headers } = options;
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      body,
      headers,
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });
  } catch (error) {
    const aborted = error instanceof Error && error.name === "TimeoutError";
    throw new UpstreamError(
      502,
      aborted ? "upstream_timeout" : "upstream_unreachable",
      `${url} ${aborted ? "timed out" : "is unreachable"}: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? (data as { detail: unknown }).detail
        : null;
    const code =
      detail && typeof detail === "object" && "code" in detail
        ? String((detail as { code: unknown }).code)
        : `http_${response.status}`;
    const message =
      detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message: unknown }).message)
        : typeof detail === "string"
          ? detail
          : `${url} returned HTTP ${response.status}`;
    throw new UpstreamError(response.status, code, message);
  }
  if (data === null) {
    throw new UpstreamError(502, "invalid_upstream_body", `${url} returned a non-JSON body`);
  }
  return data as T;
}
