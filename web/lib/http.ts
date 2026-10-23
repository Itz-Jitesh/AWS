import { ApiError } from "./api";

export const DEFAULT_TIMEOUT_MS = 30_000;

const MAX_DETAIL_CHARS = 300;

function isSafeStructuredDetail(detail: unknown): detail is { code: string; message: string } {
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return false;
  const record = detail as Record<string, unknown>;
  if (typeof record.code !== "string" || record.code.length === 0 || record.code.length > 64) {
    return false;
  }
  if (
    typeof record.message !== "string" ||
    record.message.length === 0 ||
    record.message.length > MAX_DETAIL_CHARS
  ) {
    return false;
  }
  // Structured service errors are single-line; anything longer may be a debug dump.
  return !record.message.includes("\n");
}

function extractDetailMessage(
  body: unknown,
  options: { structuredOnly?: boolean } = {},
): { message: string; code?: string } | null {
  if (typeof body === "string") {
    if (options.structuredOnly) return null;
    const text = body.trim();
    if (text && text.length <= MAX_DETAIL_CHARS) return { message: text };
    return null;
  }
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const nested = record.detail;
    if (typeof nested === "string" && !options.structuredOnly && nested.trim().length <= MAX_DETAIL_CHARS) {
      return { message: nested.trim() };
    }
    if (isSafeStructuredDetail(nested)) {
      return { message: nested.message, code: nested.code };
    }
    if (typeof record.message === "string" && record.message.length <= MAX_DETAIL_CHARS) {
      return {
        message: record.message,
        code: typeof record.code === "string" ? record.code : undefined,
      };
    }
  }
  return null;
}

export interface HttpJsonOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
  headers?: Record<string, string>;
}

export async function requestJson<T>(url: string, options: HttpJsonOptions = {}): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = { ...options.headers };
  let body: BodyInit | undefined;
  if (options.formData) {
    // jsdom's FormData lacks the toStringTag Node's fetch (undici) duck-types on.
    try {
      Object.defineProperty(options.formData, Symbol.toStringTag, {
        value: "FormData",
        configurable: true,
      });
    } catch {
      // Native browser FormData already identifies itself.
    }
    body = options.formData;
  } else if (options.body !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "GET",
      headers,
      body,
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(
        "timeout",
        `The service did not respond within ${Math.round(timeoutMs / 1000)}s.`,
      );
    }
    throw new ApiError("network", "The service could not be reached.");
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text().catch(() => "");

  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text);
    } catch {
      if (response.ok) {
        throw new ApiError("invalid_response", "The service returned a malformed response body.");
      }
    }
  }

  if (response.ok) {
    if (text.length === 0) {
      throw new ApiError("invalid_response", "The service returned an empty response body.");
    }
    return parsed as T;
  }

  const detail = extractDetailMessage(parsed);

  if (response.status === 404) {
    throw new ApiError("not_found", detail?.message ?? "The requested resource does not exist.", {
      status: 404,
      code: detail?.code,
    });
  }

  if (response.status >= 500) {
    // Only structured {code, message} service errors surface on 5xx; unstructured
    // bodies (debug dumps, HTML error pages) are never echoed to the client.
    const structured = extractDetailMessage(parsed, { structuredOnly: true });
    throw new ApiError(
      "network",
      structured
        ? `${structured.message} (${structured.code})`
        : `The service failed with HTTP ${response.status}.`,
      { status: response.status, code: structured?.code },
    );
  }

  throw new ApiError(
    "rejected",
    detail?.message ?? `The service rejected the request with HTTP ${response.status}.`,
    { status: response.status, code: detail?.code },
  );
}
