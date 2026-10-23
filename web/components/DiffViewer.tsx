"use client";

import { useMemo } from "react";
import { EmptyState } from "./Panel";

type DiffLineKind = "add" | "delete" | "context" | "hunk" | "file";

interface ParsedDiffLine {
  kind: DiffLineKind;
  oldNumber: number | null;
  newNumber: number | null;
  text: string;
}

function parseUnifiedDiff(diff: string): ParsedDiffLine[] {
  const lines = diff.split("\n");
  const parsed: ParsedDiffLine[] = [];
  let oldNumber: number | null = null;
  let newNumber: number | null = null;

  for (const raw of lines) {
    if (raw.startsWith("+++") || raw.startsWith("---")) {
      parsed.push({ kind: "file", oldNumber: null, newNumber: null, text: raw });
      continue;
    }
    if (raw.startsWith("@@")) {
      const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(raw);
      oldNumber = match ? Number(match[1]) : null;
      newNumber = match ? Number(match[2]) : null;
      parsed.push({ kind: "hunk", oldNumber: null, newNumber: null, text: raw });
      continue;
    }
    if (raw.startsWith("+")) {
      parsed.push({ kind: "add", oldNumber: null, newNumber, text: raw });
      if (newNumber !== null) newNumber += 1;
      continue;
    }
    if (raw.startsWith("-")) {
      parsed.push({ kind: "delete", oldNumber, newNumber: null, text: raw });
      if (oldNumber !== null) oldNumber += 1;
      continue;
    }
    parsed.push({ kind: "context", oldNumber, newNumber, text: raw });
    if (oldNumber !== null) oldNumber += 1;
    if (newNumber !== null) newNumber += 1;
  }

  return parsed;
}

const KIND_STYLES: Record<DiffLineKind, string> = {
  add: "bg-emerald-950/60 text-emerald-200",
  delete: "bg-red-950/60 text-red-200",
  context: "text-ink-muted",
  hunk: "bg-accent/10 text-accent",
  file: "bg-panel font-semibold text-ink",
};

export function DiffViewer({ diff }: { diff: string }) {
  const lines = useMemo(() => parseUnifiedDiff(diff), [diff]);

  if (diff.trim().length === 0) {
    return (
      <EmptyState
        message="No diff has been generated for this task."
        hint="Generate a patch to inspect the proposed unified diff."
      />
    );
  }

  return (
    <div data-testid="diff-viewer" className="flex flex-col gap-2">
      <div
        className="scrollbar-slim max-h-[32rem] overflow-auto rounded-lg border border-line bg-background"
        tabIndex={0}
        aria-label="Unified diff"
      >
        <div className="min-w-full font-mono text-xs leading-6">
          {lines.map((line, index) => (
            <div
              key={`${index}-${line.text}`}
              className={`grid grid-cols-[3rem_3rem_1fr] whitespace-pre ${KIND_STYLES[line.kind]}`}
            >
              <span className="select-none border-r border-line/60 px-2 text-right text-ink-dim">
                {line.oldNumber ?? ""}
              </span>
              <span className="select-none border-r border-line/60 px-2 text-right text-ink-dim">
                {line.newNumber ?? ""}
              </span>
              <span className="px-3">{line.text === "" ? " " : line.text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
