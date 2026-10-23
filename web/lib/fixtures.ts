import type { CheckRun, Finding, Patch, Requirement } from "./contracts";
import type { TaskRecord, TaskWorkspace } from "./api";

export const DEMO_TASK_ID = "demo";

export const DEMO_PLAN_DIGEST =
  "9f2c4b7e1a5d8c3f6b0e2a4d7c9f1b3e5a6d8c0f2b4a6d8c1e3f5a7b9c0d2e4f";

export const DEMO_BASE_DIGEST =
  "3b7d9a1c5e2f8b4a0c6d3e9f7a1b5c2d4e8f0a6b9c3d7e1f2a5b8c4d6f0e3a9b";

export const demoTask: TaskRecord = {
  task_id: DEMO_TASK_ID,
  state: "AWAITING_APPROVAL",
  goal: "Make the bucket private without deleting it.",
  mode: "build",
  created_at: "2026-10-23T09:58:12.000Z",
};

export const demoChecks: CheckRun[] = [
  {
    schema_version: "1.0.0",
    check_id: "tf-fmt",
    tool: "terraform fmt -check",
    status: "Passed",
    started_at: "2026-10-23T10:14:01.000Z",
    duration_ms: 214,
    summary: "All Terraform files are correctly formatted.",
    exit_code: 0,
    tool_version: "1.9.8",
    stdout_artifact: null,
    stderr_artifact: null,
  },
  {
    schema_version: "1.0.0",
    check_id: "tf-init",
    tool: "terraform init -backend=false",
    status: "Passed",
    started_at: "2026-10-23T10:14:02.000Z",
    duration_ms: 2410,
    summary: "Providers initialized without a backend.",
    exit_code: 0,
    tool_version: "1.9.8",
    limitations: ["Backend state is intentionally not configured in the sandbox."],
  },
  {
    schema_version: "1.0.0",
    check_id: "tf-validate",
    tool: "terraform validate",
    status: "Passed",
    started_at: "2026-10-23T10:14:05.000Z",
    duration_ms: 762,
    summary: "Configuration is valid.",
    exit_code: 0,
    tool_version: "1.9.8",
  },
  {
    schema_version: "1.0.0",
    check_id: "tf-plan",
    tool: "terraform plan -out=tfplan",
    status: "Passed",
    started_at: "2026-10-23T10:14:06.000Z",
    duration_ms: 6120,
    summary: "Plan captured: 2 to add, 1 to change, 1 to destroy.",
    exit_code: 0,
    tool_version: "1.9.8",
  },
  {
    schema_version: "1.0.0",
    check_id: "tf-show-json",
    tool: "terraform show -json tfplan",
    status: "Passed",
    started_at: "2026-10-23T10:14:12.000Z",
    duration_ms: 428,
    summary: "Plan JSON captured and redacted for analysis.",
    exit_code: 0,
    tool_version: "1.9.8",
  },
  {
    schema_version: "1.0.0",
    check_id: "checkov",
    tool: "checkov -d .",
    status: "Passed",
    started_at: "2026-10-23T10:14:13.000Z",
    duration_ms: 4231,
    summary: "0 failed checks across 41 evaluated rules on re-run.",
    exit_code: 0,
    tool_version: "3.2.333",
  },
  {
    schema_version: "1.0.0",
    check_id: "opa-baseline",
    tool: "opa eval -f pretty",
    status: "Passed",
    started_at: "2026-10-23T10:14:17.000Z",
    duration_ms: 611,
    summary: "Baseline planproof policy set returned no violations.",
    exit_code: 0,
    tool_version: "v1.4.2",
  },
  {
    schema_version: "1.0.0",
    check_id: "opa-custom-pack",
    tool: "opa eval --policy-pack custom",
    status: "NotConfigured",
    started_at: "2026-10-23T10:14:18.000Z",
    duration_ms: 0,
    summary: "Custom OPA policy pack is not configured for this task.",
    exit_code: null,
    tool_version: null,
    limitations: [
      "Custom pack rules were not evaluated and must not be read as passing.",
    ],
  },
];

export const baselineFindings: Finding[] = [
  {
    schema_version: "1.0.0",
    finding_id: "f-s3-acl",
    rule_source: "checkov",
    rule_id: "CKV_AWS_21",
    severity: "critical",
    status: "Failed",
    title: "S3 bucket ACL allows public read",
    description: "The bucket ACL grants read access to all AWS principals.",
    resource_address: "aws_s3_bucket_acl.app",
    file_path: "storage.tf",
    line_start: 22,
    evidence:
      'aws_s3_bucket_acl.app acl = "public-read" in storage.tf:22',
    remediation:
      "Remove the public ACL and attach an aws_s3_public_access_block resource.",
    fingerprint: "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  },
  {
    schema_version: "1.0.0",
    finding_id: "f-iam-wildcard",
    rule_source: "checkov",
    rule_id: "CKV_AWS_111",
    severity: "high",
    status: "Failed",
    title: "IAM policy allows wildcard actions on all resources",
    resource_address: "aws_iam_policy.upload",
    file_path: "iam.tf",
    line_start: 14,
    evidence:
      'policy_document.statement[0].Action = "*" on Resource = "*" in iam.tf:14',
    remediation: "Scope actions and resources down to the upload bucket.",
    fingerprint: "b2c3d4e5f60718293a4b5c6d7e8f9012",
  },
  {
    schema_version: "1.0.0",
    finding_id: "f-s3-logging",
    rule_source: "checkov",
    rule_id: "CKV_AWS_18",
    severity: "medium",
    status: "Failed",
    title: "S3 server access logging is not enabled",
    resource_address: "aws_s3_bucket.app",
    file_path: "storage.tf",
    line_start: 9,
    evidence: "aws_s3_bucket.app has no server_access_logging block.",
    remediation: "Enable access logging to a separate logs bucket.",
    fingerprint: "c3d4e5f60718293a4b5c6d7e8f901234",
  },
  {
    schema_version: "1.0.0",
    finding_id: "f-opa-public",
    rule_source: "opa",
    rule_id: "planproof.s3.public_acl",
    severity: "high",
    status: "Failed",
    title: "Plan preview contains a public bucket ACL",
    resource_address: "aws_s3_bucket_acl.app",
    evidence:
      "Plan resource aws_s3_bucket_acl.app has change.create acl=public-read.",
    remediation: "Drop the ACL attribute from the plan before approval.",
    fingerprint: "d4e5f60718293a4b5c6d7e8f90123456",
  },
  {
    schema_version: "1.0.0",
    finding_id: "f-custom-review",
    rule_source: "custom",
    rule_id: "planproof.custom.unrelated_change_review",
    severity: "medium",
    status: "UnableToVerify",
    title: "Unrelated change review not evaluated",
    description:
      "This rule lives in the custom OPA pack, which is not configured for this task.",
    resource_address: null,
    file_path: null,
    line_start: null,
    evidence:
      "opa eval --policy-pack custom returned NotConfigured; the rule was never evaluated.",
    remediation: "Configure a custom policy pack, then re-run the full suite.",
    fingerprint: "e5f60718293a4b5c6d7e8f9012345678",
  },
];

export const currentFindings: Finding[] = [
  {
    schema_version: "1.0.0",
    finding_id: "c-s3-acl",
    rule_source: "checkov",
    rule_id: "CKV_AWS_21",
    severity: "critical",
    status: "Passed",
    title: "S3 bucket ACL allows public read",
    resource_address: "aws_s3_public_access_block.app",
    file_path: "storage.tf",
    line_start: 31,
    evidence:
      "aws_s3_public_access_block.app blocks public_acls, public_policy, ignore_public_acls and restrict_public_buckets; public ACL removed.",
    remediation: null,
    fingerprint: "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  },
  {
    schema_version: "1.0.0",
    finding_id: "c-iam-wildcard",
    rule_source: "checkov",
    rule_id: "CKV_AWS_111",
    severity: "high",
    status: "Passed",
    title: "IAM policy allows wildcard actions on all resources",
    resource_address: "aws_iam_policy.upload",
    file_path: "iam.tf",
    line_start: 14,
    evidence:
      'policy_document.statement[0].Action is scoped to s3:PutObject on the upload bucket ARN.',
    remediation: null,
    fingerprint: "b2c3d4e5f60718293a4b5c6d7e8f9012",
  },
  {
    schema_version: "1.0.0",
    finding_id: "c-s3-logging",
    rule_source: "checkov",
    rule_id: "CKV_AWS_18",
    severity: "medium",
    status: "Passed",
    title: "S3 server access logging is not enabled",
    resource_address: "aws_s3_bucket.app",
    file_path: "storage.tf",
    line_start: 41,
    evidence:
      "aws_s3_bucket.app logs access to aws_s3_bucket.logs via server_access_logging.",
    remediation: null,
    fingerprint: "c3d4e5f60718293a4b5c6d7e8f901234",
  },
  {
    schema_version: "1.0.0",
    finding_id: "c-custom-review",
    rule_source: "custom",
    rule_id: "planproof.custom.unrelated_change_review",
    severity: "medium",
    status: "UnableToVerify",
    title: "Unrelated change review not evaluated",
    description:
      "This rule lives in the custom OPA pack, which is not configured for this task.",
    resource_address: null,
    file_path: null,
    line_start: null,
    evidence:
      "opa eval --policy-pack custom returned NotConfigured; the rule was never evaluated.",
    remediation: "Configure a custom policy pack, then re-run the full suite.",
    fingerprint: "e5f60718293a4b5c6d7e8f9012345678",
  },
];

export const demoRequirements: Requirement[] = [
  {
    schema_version: "1.0.0",
    requirement_id: "r-bucket-retained",
    text: "The existing bucket aws_s3_bucket.app must not be deleted or replaced.",
    mandatory: true,
    status: "Satisfied",
    evidence: [
      "PlanSummary destructive_actions contains only aws_s3_bucket_acl.app.",
      "aws_s3_bucket.app appears with actions [update] only.",
    ],
  },
  {
    schema_version: "1.0.0",
    requirement_id: "r-bucket-private",
    text: "The bucket must not be publicly readable after the change.",
    mandatory: true,
    status: "Satisfied",
    evidence: [
      "Checkov CKV_AWS_21 status Passed on re-run (fingerprint a1b2c3d4e5f60718293a4b5c6d7e8f90).",
      "aws_s3_public_access_block.app is created with all four block flags set.",
    ],
  },
  {
    schema_version: "1.0.0",
    requirement_id: "r-no-unrelated-changes",
    text: "No resource unrelated to bucket public access may change.",
    mandatory: false,
    status: "Unverified",
    evidence: [
      "PlanSummary lists aws_iam_policy.upload as an update, which needs manual review.",
      "Custom OPA pack returned NotConfigured, so the unrelated-change rule was not evaluated.",
    ],
    notes: "Do not read this requirement as satisfied until the rule is evaluated.",
  },
];

export const demoPatch: Patch = {
  schema_version: "1.0.0",
  patch_id: "p-1001",
  unified_diff: [
    "--- a/storage.tf",
    "+++ b/storage.tf",
    "@@ -18,10 +18,6 @@ resource \"aws_s3_bucket\" \"app\" {",
    "   bucket = \"planproof-demo-bucket\"",
    "-  acl    = \"public-read\"",
    " }",
    "",
    "+resource \"aws_s3_public_access_block\" \"app\" {",
    "+  bucket                  = aws_s3_bucket.app.id",
    "+  block_public_acls       = true",
    "+  block_public_policy     = true",
    "+  ignore_public_acls      = true",
    "+  restrict_public_buckets = true",
    "+}",
    "",
    "--- a/iam.tf",
    "+++ b/iam.tf",
    "@@ -11,8 +11,10 @@ data \"aws_iam_policy_document\" \"upload\" {",
    "   statement {",
    "-    actions   = [\"*\"]",
    "-    resources = [\"*\"]",
    "+    actions   = [\"s3:PutObject\"]",
    "+    resources = [",
    "+      \"${aws_s3_bucket.app.arn}/*\",",
    "+    ]",
    "   }",
    " }",
  ].join("\n"),
  rationale:
    "Adds an S3 public access block and scopes the upload IAM policy to the bucket, addressing the public ACL and wildcard IAM findings without touching the bucket resource itself.",
  files_changed: ["storage.tf", "iam.tf"],
  base_digest: DEMO_BASE_DIGEST,
  model_id: "mock-llm-v1",
  warnings: [
    "The public ACL resource aws_s3_bucket_acl.app is deleted by this patch; verify the destroy action before approval.",
  ],
};

export const demoWorkspace: TaskWorkspace = {
  task: demoTask,
  requirements: demoRequirements,
  checks: demoChecks,
  findings: currentFindings,
  baseline_findings: baselineFindings,
  patch: demoPatch,
  plan_summary: {
    schema_version: "1.0.0",
    plan_digest: DEMO_PLAN_DIGEST,
    create: 2,
    update: 1,
    replace: 0,
    destroy: 1,
    destructive_actions: [
      {
        address: "aws_s3_bucket_acl.app",
        actions: ["delete"],
        risk: "high",
        reason:
          "The public-read ACL resource is removed to enforce private access.",
      },
    ],
    has_changes: true,
  },
  approval: null,
};

export function buildEmptyWorkspace(task: TaskRecord): TaskWorkspace {
  return {
    task,
    requirements: [],
    checks: [],
    findings: [],
    baseline_findings: [],
    patch: null,
    plan_summary: null,
    approval: null,
  };
}
