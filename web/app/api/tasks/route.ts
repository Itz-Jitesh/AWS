import { NextResponse } from "next/server";

import { createTaskFromGit, createTaskFromUpload } from "@/lib/server/tasks";
import type { TaskMode } from "@/lib/contracts";
import { RequestError, errorResponse } from "@/lib/server/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function parseMode(value: unknown): TaskMode {
  if (value === "audit" || value === "build") return value;
  throw new RequestError(400, "bad_request", "mode must be 'audit' or 'build'");
}

function parseGoal(value: unknown): string {
  const goal = typeof value === "string" ? value.trim() : "";
  if (goal.length === 0) {
    throw new RequestError(400, "bad_request", "goal is required");
  }
  return goal;
}

export async function POST(request: Request): Promise<NextResponse> {
  try {
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("multipart/form-data")) {
      const form = await request.formData();
      const file = form.get("file");
      if (!(file instanceof File)) {
        throw new RequestError(400, "bad_request", "multipart upload requires a 'file' field");
      }
      const view = await createTaskFromUpload({
        file,
        goal: parseGoal(form.get("goal")),
        mode: parseMode(form.get("mode")),
      });
      return NextResponse.json(view, { status: 201 });
    }

    const body = (await request.json().catch(() => null)) as
      | {
          repo_source?: { kind?: string; url?: string };
          goal?: unknown;
          mode?: unknown;
        }
      | null;
    if (!body || typeof body !== "object") {
      throw new RequestError(400, "bad_request", "request body must be JSON");
    }
    if (body.repo_source?.kind !== "git_url" || !body.repo_source.url) {
      throw new RequestError(
        400,
        "bad_request",
        "JSON task creation supports only repo_source.kind='git_url' with a url; use multipart for ZIP uploads",
      );
    }
    const view = await createTaskFromGit({
      url: body.repo_source.url,
      goal: parseGoal(body.goal),
      mode: parseMode(body.mode),
    });
    return NextResponse.json(view, { status: 201 });
  } catch (error) {
    return errorResponse(error);
  }
}
