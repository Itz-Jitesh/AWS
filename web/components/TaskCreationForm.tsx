"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import type { CreateTaskInput, RepoSource } from "@/lib/api";
import type { TaskMode } from "@/lib/contracts";
import { Banner } from "./Panel";

type SourceKind = RepoSource["kind"];

const MODES: Array<{
  value: TaskMode;
  title: string;
  description: string;
}> = [
  {
    value: "audit",
    title: "Audit",
    description:
      "Run fmt, validate, Checkov and OPA, then report normalized findings. No patch is proposed.",
  },
  {
    value: "build",
    title: "Build",
    description:
      "Audit, then generate a minimal patch, re-run the full check suite, and gate approval on the plan digest.",
  },
];

function isValidGitUrl(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length === 0) return false;
  if (/^git@[\w.-]+:[\w./-]+(?:\.git)?$/.test(trimmed)) return true;
  if (/^(ssh|git):\/\/[^\s]+$/.test(trimmed)) return true;
  if (/^https?:\/\/[^\s]+$/.test(trimmed)) {
    try {
      const parsed = new URL(trimmed);
      return parsed.hostname.length > 0;
    } catch {
      return false;
    }
  }
  return false;
}

export function TaskCreationForm({
  onSubmit,
}: {
  onSubmit: (input: CreateTaskInput) => Promise<void>;
}) {
  const [sourceKind, setSourceKind] = useState<SourceKind>("zip");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [gitUrl, setGitUrl] = useState("");
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<TaskMode>("build");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function validate(): { input: CreateTaskInput | null; next: Record<string, string> } {
    const next: Record<string, string> = {};

    if (sourceKind === "zip") {
      if (!zipFile) {
        next.source = "Choose a Terraform repository ZIP file.";
      } else if (!zipFile.name.toLowerCase().endsWith(".zip")) {
        next.source = "The uploaded file must have a .zip extension.";
      }
    } else if (!isValidGitUrl(gitUrl)) {
      next.source = "Enter a valid Git URL, for example https://host/org/repo.git.";
    }

    const trimmedGoal = goal.trim();
    if (trimmedGoal.length === 0) {
      next.goal = "Describe the infrastructure goal for this task.";
    } else if (trimmedGoal.length < 10) {
      next.goal = "The goal must be at least 10 characters so requirements can be extracted.";
    }

    if (sourceKind === "zip") {
      return {
        input:
          Object.keys(next).length === 0 && zipFile
            ? {
                repo_source: { kind: "zip", filename: zipFile.name, file: zipFile },
                goal: trimmedGoal,
                mode,
              }
            : null,
        next,
      };
    }

    return {
      input:
        Object.keys(next).length === 0
          ? {
              repo_source: { kind: "git_url", url: gitUrl.trim() },
              goal: trimmedGoal,
              mode,
            }
          : null,
      next,
    };
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);

    const { input, next } = validate();
    setErrors(next);
    if (!input) return;

    setSubmitting(true);
    try {
      await onSubmit(input);
    } catch (error) {
      setSubmitError(
        error instanceof Error ? error.message : "Task creation failed.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const inputClass =
    "w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-sm text-ink placeholder:text-ink-dim focus:border-accent focus:outline-none";

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      data-testid="task-form"
      className="flex flex-col gap-5"
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="flex flex-col rounded-xl border border-line bg-panel p-5">
          <div>
            <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">
              Repository source
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Upload a ZIP archive or point at a public Git repository.
            </p>
          </div>

          <div
            role="radiogroup"
            aria-label="Repository source type"
            className="mt-4 grid grid-cols-2 gap-2 rounded-lg border border-line bg-surface p-1"
          >
            {(
              [
                { value: "zip", label: "ZIP upload" },
                { value: "git_url", label: "Git URL" },
              ] as Array<{ value: SourceKind; label: string }>
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={sourceKind === option.value}
                onClick={() => setSourceKind(option.value)}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  sourceKind === option.value
                    ? "bg-accent/20 text-ink shadow-[inset_0_0_0_1px_var(--color-accent)]"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div className="mt-4 flex-1">
            {sourceKind === "zip" ? (
              <div>
                <label
                  htmlFor="repo-zip"
                  className="block text-xs font-medium tracking-wide text-ink-muted uppercase"
                >
                  Terraform repository (.zip)
                </label>
                <input
                  id="repo-zip"
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,application/zip"
                  className="mt-2 w-full cursor-pointer rounded-lg border border-dashed border-line-strong bg-surface px-3 py-3 text-sm text-ink-muted file:mr-3 file:rounded-md file:border-0 file:bg-line-strong file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-ink"
                  onChange={(event) => {
                    setZipFile(event.target.files?.[0] ?? null);
                    setErrors((current) => ({ ...current, source: "" }));
                  }}
                />
                <p className="mt-2 text-xs text-ink-dim">
                  Archive paths are validated server side. Do not include state files
                  or credentials in the archive.
                </p>
              </div>
            ) : (
              <div>
                <label
                  htmlFor="repo-url"
                  className="block text-xs font-medium tracking-wide text-ink-muted uppercase"
                >
                  Public Git URL
                </label>
                <input
                  id="repo-url"
                  type="url"
                  inputMode="url"
                  placeholder="https://github.com/org/repo.git"
                  value={gitUrl}
                  onChange={(event) => {
                    setGitUrl(event.target.value);
                    setErrors((current) => ({ ...current, source: "" }));
                  }}
                  aria-invalid={Boolean(errors.source)}
                  className={`mt-2 ${inputClass} font-mono`}
                />
              </div>
            )}
            {errors.source ? (
              <p role="alert" className="mt-2 text-xs font-medium text-red-400">
                {errors.source}
              </p>
            ) : null}
          </div>
        </section>

        <section className="flex flex-col rounded-xl border border-line bg-panel p-5">
          <div>
            <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">
              Goal and mode
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              The goal is stored as mandatory requirements and re-checked after every
              patch.
            </p>
          </div>

          <div className="mt-4 flex-1">
            <label
              htmlFor="goal"
              className="block text-xs font-medium tracking-wide text-ink-muted uppercase"
            >
              Infrastructure goal
            </label>
            <textarea
              id="goal"
              rows={5}
              value={goal}
              onChange={(event) => {
                setGoal(event.target.value);
                setErrors((current) => ({ ...current, goal: "" }));
              }}
              aria-invalid={Boolean(errors.goal)}
              placeholder="Make the bucket private without deleting it."
              className={`mt-2 resize-y ${inputClass}`}
            />
            {errors.goal ? (
              <p role="alert" className="mt-2 text-xs font-medium text-red-400">
                {errors.goal}
              </p>
            ) : null}
          </div>

          <fieldset className="mt-4">
            <legend className="text-xs font-medium tracking-wide text-ink-muted uppercase">
              Mode
            </legend>
            <div className="mt-2 flex flex-col gap-2">
              {MODES.map((option) => (
                <label
                  key={option.value}
                  className={`flex cursor-pointer gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                    mode === option.value
                      ? "border-accent/70 bg-accent/10"
                      : "border-line bg-surface hover:border-line-strong"
                  }`}
                >
                  <input
                    type="radio"
                    name="mode"
                    value={option.value}
                    checked={mode === option.value}
                    onChange={() => setMode(option.value)}
                    className="mt-1 accent-[var(--color-accent)]"
                  />
                  <span>
                    <span className="block text-sm font-semibold text-ink">
                      {option.title}
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-ink-muted">
                      {option.description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </section>
      </div>

      {submitError ? (
        <Banner tone="danger" title="Task creation failed">
          <p>{submitError}</p>
        </Banner>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-ink-dim">
          Applying infrastructure is not part of the MVP. Approval stops at a plan
          digest.
        </p>
        <div className="flex items-center gap-3">
          <Link
            href="/tasks/demo"
            className="rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
          >
            Explore demo workspace
          </Link>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-background transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create task"}
          </button>
        </div>
      </div>
    </form>
  );
}
