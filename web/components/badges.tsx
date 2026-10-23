import type {
  CheckStatus,
  DestructiveRisk,
  RequirementStatus,
  Severity,
  TaskState,
} from "@/lib/contracts";
import {
  checkStatusTone,
  requirementTone,
  severityTone,
  taskStateLabel,
  taskStateTone,
} from "@/lib/ui";

const RISK_TONES: Record<DestructiveRisk, string> = {
  high: "border-red-500/70 bg-red-950 text-red-300",
  medium: "border-amber-500/60 bg-amber-950 text-amber-300",
  low: "border-zinc-600 bg-zinc-900 text-zinc-300",
};

function Badge({
  label,
  className,
  testId,
}: {
  label: string;
  className: string;
  testId?: string;
}) {
  return (
    <span
      data-testid={testId}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${className}`}
    >
      {label}
    </span>
  );
}

export function StatusBadge({
  status,
  testId,
}: {
  status: CheckStatus;
  testId?: string;
}) {
  const tone = checkStatusTone(status);
  return (
    <span
      data-testid={testId ?? `status-${status}`}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${tone.badge}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
      {tone.label}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const tone = severityTone(severity);
  return <Badge label={tone.label} className={tone.badge} />;
}

export function RequirementStatusBadge({ status }: { status: RequirementStatus }) {
  const tone = requirementTone(status);
  return (
    <span
      data-testid={`requirement-${status}`}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${tone.badge}`}
    >
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
      {tone.label}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: DestructiveRisk }) {
  return <Badge label={`${risk.toUpperCase()} RISK`} className={RISK_TONES[risk]} />;
}

export function StateBadge({ state }: { state: TaskState }) {
  return (
    <span
      data-testid="task-state"
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide uppercase ${taskStateTone(state)}`}
    >
      {taskStateLabel(state)}
    </span>
  );
}
