import type { CheckStatus, Severity, TaskState } from "./contracts";

export interface Tone {
  label: string;
  badge: string;
  dot: string;
}

const CHECK_STATUS_TONES: Record<CheckStatus, Tone> = {
  Passed: {
    label: "Passed",
    badge: "border-emerald-700/60 bg-emerald-950/70 text-emerald-300",
    dot: "bg-emerald-400",
  },
  Failed: {
    label: "Failed",
    badge: "border-red-700/60 bg-red-950/70 text-red-300",
    dot: "bg-red-400",
  },
  Skipped: {
    label: "Skipped",
    badge: "border-zinc-600 bg-zinc-900 text-zinc-400",
    dot: "bg-zinc-500",
  },
  NotConfigured: {
    label: "Not configured",
    badge: "border-amber-700/60 bg-amber-950/60 text-amber-300",
    dot: "bg-amber-400",
  },
  UnableToVerify: {
    label: "Unable to verify",
    badge: "border-amber-700/60 bg-amber-950/60 text-amber-300",
    dot: "bg-amber-400",
  },
};

export function checkStatusTone(status: CheckStatus): Tone {
  return CHECK_STATUS_TONES[status];
}

export const ALL_CHECK_STATUSES: CheckStatus[] = [
  "Passed",
  "Failed",
  "Skipped",
  "NotConfigured",
  "UnableToVerify",
];

const SEVERITY_TONES: Record<Severity, Tone> = {
  critical: {
    label: "Critical",
    badge: "border-red-500/70 bg-red-950 text-red-300",
    dot: "bg-red-400",
  },
  high: {
    label: "High",
    badge: "border-orange-500/70 bg-orange-950 text-orange-300",
    dot: "bg-orange-400",
  },
  medium: {
    label: "Medium",
    badge: "border-amber-500/60 bg-amber-950 text-amber-300",
    dot: "bg-amber-400",
  },
  low: {
    label: "Low",
    badge: "border-sky-600/60 bg-sky-950 text-sky-300",
    dot: "bg-sky-400",
  },
  info: {
    label: "Info",
    badge: "border-zinc-600 bg-zinc-900 text-zinc-300",
    dot: "bg-zinc-400",
  },
  unknown: {
    label: "Unknown",
    badge: "border-zinc-600 border-dashed bg-zinc-900 text-zinc-400",
    dot: "bg-zinc-500",
  },
};

export function severityTone(severity: Severity): Tone {
  return SEVERITY_TONES[severity];
}

const REQUIREMENT_TONES: Record<string, Tone> = {
  Satisfied: {
    label: "Satisfied",
    badge: "border-emerald-700/60 bg-emerald-950/70 text-emerald-300",
    dot: "bg-emerald-400",
  },
  Unverified: {
    label: "Unverified",
    badge: "border-amber-700/60 bg-amber-950/60 text-amber-300",
    dot: "bg-amber-400",
  },
  Violated: {
    label: "Violated",
    badge: "border-red-700/60 bg-red-950/70 text-red-300",
    dot: "bg-red-400",
  },
};

export function requirementTone(status: string): Tone {
  return REQUIREMENT_TONES[status] ?? {
    label: status,
    badge: "border-zinc-600 bg-zinc-900 text-zinc-400",
    dot: "bg-zinc-500",
  };
}

const TASK_STATE_LABELS: Record<TaskState, string> = {
  CREATED: "Created",
  CONTEXT_GATHERING: "Gathering context",
  REQUIREMENTS_READY: "Requirements ready",
  PROPOSED: "Patch proposed",
  CHECKING: "Checking",
  REPAIRING: "Repairing",
  REVIEW_READY: "Review ready",
  AWAITING_APPROVAL: "Awaiting approval",
  COMPLETE: "Complete",
};

export function taskStateLabel(state: TaskState): string {
  return TASK_STATE_LABELS[state] ?? state;
}

const TASK_STATE_TONES: Record<TaskState, string> = {
  CREATED: "border-zinc-600 bg-zinc-900 text-zinc-300",
  CONTEXT_GATHERING: "border-sky-600/60 bg-sky-950 text-sky-300",
  REQUIREMENTS_READY: "border-sky-600/60 bg-sky-950 text-sky-300",
  PROPOSED: "border-sky-600/60 bg-sky-950 text-sky-300",
  CHECKING: "border-amber-700/60 bg-amber-950/60 text-amber-300",
  REPAIRING: "border-amber-700/60 bg-amber-950/60 text-amber-300",
  REVIEW_READY: "border-indigo-600/60 bg-indigo-950 text-indigo-300",
  AWAITING_APPROVAL: "border-indigo-600/60 bg-indigo-950 text-indigo-300",
  COMPLETE: "border-emerald-700/60 bg-emerald-950/70 text-emerald-300",
};

export function taskStateTone(state: TaskState): string {
  return TASK_STATE_TONES[state] ?? "border-zinc-600 bg-zinc-900 text-zinc-300";
}

export function severityRank(severity: Severity): number {
  switch (severity) {
    case "critical":
      return 0;
    case "high":
      return 1;
    case "medium":
      return 2;
    case "low":
      return 3;
    case "info":
      return 4;
    default:
      return 5;
  }
}

export function statusRank(status: CheckStatus): number {
  switch (status) {
    case "Failed":
      return 0;
    case "UnableToVerify":
      return 1;
    case "NotConfigured":
      return 2;
    case "Skipped":
      return 3;
    default:
      return 4;
  }
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function shortDigest(digest: string | null | undefined): string {
  if (!digest) return "";
  return `${digest.slice(0, 12)}…${digest.slice(-8)}`;
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, "Z");
}

export function isBlockingStatus(status: CheckStatus): boolean {
  return status === "Failed" || status === "UnableToVerify";
}
