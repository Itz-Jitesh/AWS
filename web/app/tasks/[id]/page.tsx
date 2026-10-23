"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TaskWorkspace } from "@/components/TaskWorkspace";

function TaskRoute() {
  const params = useParams<{ id: string }>();
  const taskId = typeof params?.id === "string" ? params.id : "";

  if (!taskId) {
    return <p className="text-sm text-ink-muted">Missing task id.</p>;
  }

  return <TaskWorkspace key={taskId} taskId={taskId} />;
}

export default function TaskPage() {
  return (
    <AppShell>
      <Suspense
        fallback={
          <div className="flex flex-col gap-4">
            {[0, 1, 2].map((row) => (
              <div
                key={row}
                className="h-40 animate-pulse rounded-xl border border-line bg-panel"
              />
            ))}
          </div>
        }
      >
        <TaskRoute />
      </Suspense>
    </AppShell>
  );
}
