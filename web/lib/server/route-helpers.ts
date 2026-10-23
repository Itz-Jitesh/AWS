import { RequestError } from "./upstream";

export async function taskIdFrom(context: {
  params: Promise<{ id: string }>;
}): Promise<string> {
  const { id } = await context.params;
  if (!/^[0-9a-f]{32}$/.test(id)) {
    throw new RequestError(400, "invalid_task_id", "invalid task id");
  }
  return id;
}

export async function jsonBody<T>(request: Request): Promise<T> {
  try {
    return (await request.json()) as T;
  } catch {
    throw new RequestError(400, "bad_request", "request body must be valid JSON");
  }
}
