import { NextResponse } from "next/server";

import { extractRequirements } from "@/lib/server/tasks";
import { taskIdFrom } from "@/lib/server/route-helpers";
import { errorResponse } from "@/lib/server/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 900;

export async function POST(
  _request: Request,
  context: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  try {
    const taskId = await taskIdFrom(context);
    return NextResponse.json(await extractRequirements(taskId));
  } catch (error) {
    return errorResponse(error);
  }
}
