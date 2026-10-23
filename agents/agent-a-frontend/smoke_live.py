#!/usr/bin/env python3
"""PlanProof Agent A — live end-to-end integration smoke test.

Drives the real Next.js frontend against the real worker service (Agent B)
and ai service (Agent C). No mocks: the frontend must be started with
NEXT_PUBLIC_WORKER_URL and NEXT_PUBLIC_AI_URL pointing at live services.

Usage:
  python3 smoke_live.py \
      --frontend http://127.0.0.1:3000 \
      --worker   http://127.0.0.1:8081 \
      --ai       http://127.0.0.1:8082

Prerequisites:
  * worker service running (uvicorn app.main:app) with contracts/ present
    at the repository root, terraform NOT required (absent tool => every
    check must report UnableToVerify, never Passed)
  * ai service running (uvicorn planproof_ai.app:app)
  * frontend dev/prod server running with live env vars
  * python3 with the `playwright` package (chromium installed)

Exit code 0 = every check passed; 1 = at least one failed.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

MAIN_TF = """\
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.31.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "app" {
  bucket = "planproof-live-smoke-bucket"
}

resource "aws_s3_bucket_public_access_block" "app" {
  bucket                  = aws_s3_bucket.app.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
"""

GOAL = "Make the bucket private without deleting it and block all public access."

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    line = ("PASS " if ok else "FAIL ") + name
    if detail and not ok:
        line += f"  [{detail}]"
    print(line, flush=True)


def build_fixture(tmpdir: Path) -> Path:
    zip_path = tmpdir / "live-smoke-fixture.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.tf", MAIN_TF)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", default="http://127.0.0.1:3000")
    parser.add_argument("--worker", default="http://127.0.0.1:8081")
    parser.add_argument("--ai", default="http://127.0.0.1:8082")
    parser.add_argument("--shots", default="/tmp/planproof-live-shots")
    args = parser.parse_args()

    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix="planproof-smoke-"))
    fixture = build_fixture(tmpdir)

    page_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        # 1. Home renders in live mode (never the mock backend).
        page.goto(args.frontend, wait_until="networkidle")
        chip = page.get_by_test_id("data-source").inner_text()
        check(
            "backend chip reports live worker (direct)",
            "live worker (direct)" in chip.lower(),
            chip,
        )
        page.screenshot(path=str(shots / "01-home-live.png"), full_page=True)

        # Hydration probe: the source-kind radios are React-controlled. Flip
        # them to confirm the client handler is attached before submitting,
        # otherwise the browser would do a native GET form submit.
        page.get_by_role("radio", name="Git URL").click()
        page.wait_for_selector(
            'button[role="radio"]:has-text("Git URL")[aria-checked="true"]',
            timeout=15_000,
        )
        page.get_by_role("radio", name="ZIP upload").click()
        page.wait_for_selector(
            'button[role="radio"]:has-text("ZIP upload")[aria-checked="true"]',
            timeout=15_000,
        )
        check("task form hydrated (react-controlled radios respond)", True)

        # 2. Create a real task from a real ZIP upload (POST /ingest/upload).
        page.set_input_files("#repo-zip", str(fixture))
        page.fill("#goal", GOAL)
        page.click('button[type="submit"]')
        page.wait_for_url(re.compile(r"/tasks/[0-9a-f]{32}"), timeout=45_000)
        task_id = page.url.rsplit("/", 1)[-1]
        check(
            "task id is worker's 32-hex format",
            re.fullmatch(r"[0-9a-f]{32}", task_id) is not None,
            page.url,
        )

        page.get_by_test_id("task-workspace").wait_for(timeout=45_000)

        # 3. Real ingest metadata rendered (tf files + providers from the ZIP).
        ingest = page.get_by_test_id("ingest-summary").inner_text()
        check(
            "ingest summary shows detected .tf file and aws provider",
            ".tf file" in ingest and "aws" in ingest,
            ingest,
        )

        # 4. Service status notice lists operations that are genuinely blocked.
        #    inner_text() returns rendered layout, so normalize whitespace and case.
        notice = " ".join(page.get_by_test_id("service-notice").inner_text().split())
        for label in (
            "Findings (unavailable)",
            "Patch generation (unavailable)",
            "Approval (unavailable)",
            "Evidence report export (unavailable)",
        ):
            check(f"service notice: {label}", label in notice, notice[:400])

        # 5. Blocked operations fail closed in the UI.
        check(
            "generate patch disabled",
            page.get_by_test_id("generate-patch").is_disabled(),
        )
        check(
            "approve disabled before any plan",
            page.get_by_test_id("approve-button").is_disabled(),
        )
        check(
            "report download hidden (endpoint missing)",
            page.get_by_test_id("download-report").count() == 0,
        )
        check(
            "report-unavailable explanation shown",
            page.get_by_test_id("report-unavailable").count() == 1,
        )
        check(
            "state marked client-derived (DEC-04 note)",
            page.get_by_test_id("state-derived-note").count() == 1,
        )
        page.screenshot(path=str(shots / "02-ingested.png"), full_page=True)

        # 6. Real check suite via worker POST /check (terraform absent locally).
        page.get_by_test_id("run-checks").click()
        page.get_by_test_id("banner-unverified-checks").wait_for(timeout=180_000)
        status_count = page.locator('[data-testid^="check-status-"]').count()
        unable = page.locator('[data-testid^="check-status-"]').filter(
            has_text="Unable to verify"
        )
        check("all five checks rendered", status_count == 5, str(status_count))
        check(
            "every check reports UnableToVerify (no false pass)",
            unable.count() == 5,
            f"{unable.count()}/5",
        )
        check(
            "unverified banner shown (never 'passed')",
            page.get_by_test_id("banner-unverified-checks").count() == 1,
        )
        state_text = page.get_by_test_id("task-state").inner_text()
        check(
            "client-derived state is CHECKING",
            "checking" in state_text.lower(),
            state_text,
        )
        page.screenshot(path=str(shots / "03-checks-ran.png"), full_page=True)

        # 7. Plan capture against the real worker (no plan => explicit reason).
        page.get_by_test_id("capture-plan").click()
        page.get_by_test_id("capture-unavailable").wait_for(timeout=30_000)
        capture_text = page.get_by_test_id("capture-unavailable").inner_text()
        check(
            "capture-unavailable reason surfaced from worker",
            "no plan artifact" in capture_text,
            capture_text,
        )
        check(
            "approve still disabled after capture attempt",
            page.get_by_test_id("approve-button").is_disabled(),
        )

        # 8. Requirements extraction against the real ai service. The service
        #    currently fails (mock LLM has no preset responses); the frontend
        #    must surface the structured error, never invent requirements.
        page.get_by_test_id("extract-requirements").click()
        page.get_by_test_id("action-error").wait_for(timeout=30_000)
        error_text = page.get_by_test_id("action-error").inner_text()
        check(
            "ai failure surfaced honestly (no invented requirements)",
            "llm_response_invalid" in error_text or "preset responses" in error_text,
            error_text,
        )
        check(
            "no requirements fabricated after failure",
            page.locator('[data-testid^="requirement-"]').count() == 0,
        )
        page.screenshot(path=str(shots / "04-final-state.png"), full_page=True)

        check("no uncaught page errors", not page_errors, "; ".join(page_errors[:3]))
        browser.close()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} checks passed. Screenshots: {shots}")
    if passed != total:
        print("FAILED:", ", ".join(name for name, ok, _ in results if not ok))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
