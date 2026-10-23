"use client";

import { useRouter } from "next/navigation";
import type { CreateTaskInput } from "@/lib/api";
import { getApiClient } from "@/lib/client";
import { AppShell } from "@/components/AppShell";
import { TaskCreationForm } from "@/components/TaskCreationForm";

const HIGHLIGHTS = [
  {
    title: "Deterministic checks",
    body: "fmt, validate, plan, Checkov and OPA run from fixed command arrays. A missing tool is reported as unable to verify, never as a pass.",
  },
  {
    title: "Minimal patches",
    body: "Repairs are unified diffs against the current base digest, with a bounded repair loop and a full re-check after every attempt.",
  },
  {
    title: "Human approval",
    body: "Approval is bound to the exact plan digest. Destructive plan actions are surfaced before consent is recorded.",
  },
];

export default function HomePage() {
  const router = useRouter();

  async function handleSubmit(input: CreateTaskInput) {
    const task = await getApiClient().createTask(input);
    router.push(`/tasks/${encodeURIComponent(task.task_id)}`);
  }

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <section className="flex flex-col gap-4">
          <p className="text-xs font-semibold tracking-[0.2em] text-accent uppercase">
            AI infrastructure engineering harness
          </p>
          <h1 className="max-w-3xl text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Audit Terraform, repair it minimally, and gate every change on evidence.
          </h1>
          <p className="max-w-2xl text-base leading-relaxed text-ink-muted">
            Upload a repository or point at a Git URL, describe your goal, and
            PlanProof collects findings, proposes a minimal patch, re-runs the full
            check suite, and waits for your approval on the exact plan digest.
          </p>

          <dl className="mt-2 grid gap-3 sm:grid-cols-3">
            {HIGHLIGHTS.map((highlight) => (
              <div
                key={highlight.title}
                className="rounded-xl border border-line bg-panel px-4 py-4"
              >
                <dt className="text-sm font-semibold text-ink">{highlight.title}</dt>
                <dd className="mt-1.5 text-sm leading-relaxed text-ink-muted">
                  {highlight.body}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="rounded-xl border border-line bg-panel/60 p-5 sm:p-6">
          <div className="mb-5">
            <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">
              New task
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Single-user, single-project demo. Nothing is applied to your cloud
              account.
            </p>
          </div>
          <TaskCreationForm onSubmit={handleSubmit} />
        </section>
      </div>
    </AppShell>
  );
}
