import { NextResponse } from "next/server";

import { MANDATORY_CHECKS, serverConfig } from "@/lib/server/config";
import { serviceCapabilities } from "@/lib/server/tasks";
import { errorResponse } from "@/lib/server/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  try {
    const services = await serviceCapabilities();
    const aiHealth = services.ai.health as
      | { model_backend?: string; model_id?: string }
      | null;
    const modelConfigured = Boolean(aiHealth?.model_backend && aiHealth.model_backend !== "mock");
    return NextResponse.json({
      status: "ok",
      services,
      model: {
        backend: aiHealth?.model_backend ?? null,
        model_id: aiHealth?.model_id ?? null,
        configured: modelConfigured,
        mock_mode: aiHealth?.model_backend === "mock",
      },
      checks: { mandatory: MANDATORY_CHECKS, client_selectable: false },
      paths: {
        worker: serverConfig.workerUrl,
        ai: serverConfig.aiUrl,
        audit: serverConfig.auditUrl,
        ollama: serverConfig.ollamaUrl,
      },
    });
  } catch (error) {
    return errorResponse(error);
  }
}
