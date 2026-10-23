import { NextResponse } from "next/server";

import { approveTask } from "@/lib/server/tasks";
import { jsonBody, taskIdFrom } from "@/lib/server/route-helpers";
import { RequestError, errorResponse } from "@/lib/server/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  try {
    const taskId = await taskIdFrom(context);
    const body = await jsonBody<{ plan_digest?: unknown }>(request);
    const digest = typeof body.plan_digest === "string" ? body.plan_digest.trim() : "";
    if (!/^[0-9a-f]{64}$/.test(digest)) {
      throw new RequestError(
        400,
        "bad_request",
        "plan_digest must be the 64-hex canonical plan digest",
      );
    }
    return NextResponse.json(await approveTask(taskId, digest));
  } catch (error) {
    return errorResponse(error);
  }
}
