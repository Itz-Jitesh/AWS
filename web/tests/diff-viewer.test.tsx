import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DiffViewer } from "@/components/DiffViewer";
import { PatchPanel } from "@/components/PatchPanel";
import { demoPatch } from "@/lib/fixtures";

const SAMPLE_DIFF = [
  "--- a/main.tf",
  "+++ b/main.tf",
  "@@ -1,4 +1,6 @@",
  ' resource "aws_s3_bucket" "app" {',
  '-  acl    = "public-read"',
  "+  # private by default",
  "+  force_destroy = false",
  " }",
].join("\n");

describe("DiffViewer", () => {
  it("renders added and removed lines with file headers", () => {
    render(<DiffViewer diff={SAMPLE_DIFF} />);

    const viewer = screen.getByTestId("diff-viewer");
    expect(viewer).toHaveTextContent("--- a/main.tf");
    expect(viewer).toHaveTextContent("+++ b/main.tf");
    expect(viewer).toHaveTextContent("- acl");
    expect(viewer).toHaveTextContent(/\+ force_destroy = false/);
  });

  it("renders an empty state when no diff exists", () => {
    render(<DiffViewer diff="" />);
    expect(screen.getByText("No diff has been generated for this task.")).toBeInTheDocument();
  });
});

describe("PatchPanel", () => {
  it("renders rationale, warnings and file list for the demo patch", () => {
    render(<PatchPanel patch={demoPatch} />);

    expect(screen.getByTestId("patch-panel")).toHaveTextContent("p-1001");
    expect(screen.getByText(/public ACL resource aws_s3_bucket_acl\.app is deleted/i)).toBeInTheDocument();
    expect(screen.getByText("storage.tf")).toBeInTheDocument();
    expect(screen.getByText("iam.tf")).toBeInTheDocument();
    expect(screen.getByTestId("diff-viewer")).toBeInTheDocument();
  });

  it("renders an empty state without a patch", () => {
    render(<PatchPanel patch={null} />);
    expect(screen.getByText("No patch proposed yet.")).toBeInTheDocument();
  });
});
