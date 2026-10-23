import pytest

from helpers import (
    BASE_LINES,
    json_requirements_response,
    rationale_response,
    secret_check,
    tf_response,
    unified_append,
    unified_replace,
)
from planproof_ai.config import AIConfig
from planproof_ai.contracts import CheckStatus, RequirementStatus
from planproof_ai.errors import LLMResponseError
from planproof_ai.llm.mock import MockLLMAdapter
from planproof_ai.repair import (
    StopReason,
    build_diagnostics,
    is_regression,
    repair_loop,
    suite_passed,
)
from planproof_ai.testing import MockAuditClient, MockWorkerClient, make_check, make_requirement

FAILING = [make_check("fmt", CheckStatus.FAILED, tool="terraform", exit_code=3,
                      summary="terraform fmt found issues")]
PASSING = [make_check("fmt", CheckStatus.PASSED, tool="terraform", summary="fmt clean")]
SECRET_FAILING = [make_check("fmt", CheckStatus.FAILED, **secret_check())]

EVIL_DIFF = "--- a/../evil.tf\n+++ b/../evil.tf\n@@ -1,1 +1,1 @@\n-x\n+y\n"


def req(text: str = "bucket must be private", status: str = "Unverified"):
    return make_requirement(text, status=status)


def satisfied(requirements, diff, plan):
    return [
        make_requirement(r.text, r.requirement_id, r.mandatory, "Satisfied", ["evidence: plan diff"])
        for r in requirements
    ]


def test_suite_and_regression_helpers():
    assert suite_passed(PASSING)
    assert not suite_passed(FAILING)
    assert not suite_passed([])
    both_pass = [make_check("fmt", CheckStatus.PASSED), make_check("validate", CheckStatus.PASSED)]
    validate_fails = [
        make_check("fmt", CheckStatus.PASSED),
        make_check("validate", CheckStatus.FAILED, exit_code=1),
    ]
    assert is_regression(both_pass, validate_fails)
    assert is_regression(PASSING, [make_check("fmt", CheckStatus.FAILED, exit_code=3)])
    assert is_regression(PASSING, [])
    assert not is_regression(FAILING, PASSING)
    assert not is_regression(FAILING, FAILING)


def test_build_diagnostics_redacts_secrets(config: AIConfig):
    diagnostics = build_diagnostics(SECRET_FAILING, [req()], "", config)
    assert "hunter2" not in diagnostics
    assert "AKIA1234567890ABCDEF" not in diagnostics
    assert "***REDACTED***" in diagnostics
    assert "fmt" in diagnostics


def test_happy_path_resolves(workspace, config: AIConfig):
    patch_diff = unified_replace(
        "main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"'
    )
    llm = MockLLMAdapter([tf_response(patch_diff)])
    worker = MockWorkerClient(suites=[FAILING, PASSING])
    audit = MockAuditClient(intent_fn=satisfied)

    result = repair_loop(
        "t1", workspace, llm=llm, worker=worker, audit=audit,
        requirements=[req()], max_attempts=3, config=config,
    )

    assert result.success is True
    assert result.stop_reason == StopReason.RESOLVED
    assert len(result.attempts) == 1
    assert result.attempts[0].applied is True
    assert result.attempts[0].patch is not None
    assert len(worker.check_calls) == 2
    assert result.checks[0].status == CheckStatus.PASSED
    assert result.requirements[0].status == RequirementStatus.SATISFIED
    assert "main.tf" in result.applied_diff
    content = open(workspace + "/main.tf", encoding="utf-8").read()
    assert "demo-private" in content


def test_requirements_not_met_stops_safely(workspace, config: AIConfig):
    lines0 = list(BASE_LINES)
    lines1 = lines0 + ["# r1"]
    lines2 = lines1 + ["# r2"]
    llm = MockLLMAdapter([
        tf_response(unified_append("main.tf", lines0, "# r1")),
        tf_response(unified_append("main.tf", lines1, "# r2")),
        tf_response(unified_append("main.tf", lines2, "# r3")),
    ])
    worker = MockWorkerClient(suites=[PASSING])
    audit = MockAuditClient()

    result = repair_loop(
        "t2", workspace, llm=llm, worker=worker, audit=audit,
        requirements=[req("bucket must be private")], max_attempts=3, config=config,
    )

    assert result.success is False
    assert result.stop_reason == StopReason.REQUIREMENTS_NOT_MET
    assert len(result.attempts) == 3
    assert all(a.applied for a in result.attempts)
    assert len(worker.check_calls) == 4
    assert result.requirements[0].status == RequirementStatus.UNVERIFIED


def test_attempts_are_clamped_to_three(workspace, config: AIConfig):
    lines0 = list(BASE_LINES)
    lines1 = lines0 + ["# r1"]
    lines2 = lines1 + ["# r2"]
    llm = MockLLMAdapter([
        tf_response(unified_append("main.tf", lines0, "# r1")),
        tf_response(unified_append("main.tf", lines1, "# r2")),
        tf_response(unified_append("main.tf", lines2, "# r3")),
    ])
    worker = MockWorkerClient(suites=[FAILING])
    audit = MockAuditClient()

    result = repair_loop(
        "t3", workspace, llm=llm, worker=worker, audit=audit,
        requirements=[req()], max_attempts=99, config=config,
    )

    assert result.stop_reason == StopReason.ATTEMPTS_EXHAUSTED
    assert len(result.attempts) == 3
    assert len(worker.check_calls) == 4


def test_unsafe_patch_stops_loop(workspace, config: AIConfig):
    llm = MockLLMAdapter([tf_response(EVIL_DIFF)])
    worker = MockWorkerClient(suites=[FAILING])
    audit = MockAuditClient()

    result = repair_loop(
        "t4", workspace, llm=llm, worker=worker, audit=audit,
        requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.UNSAFE_PATCH
    assert result.success is False
    assert len(result.attempts) == 1
    assert result.attempts[0].applied is False
    assert len(worker.check_calls) == 1
    content = open(workspace + "/main.tf", encoding="utf-8").read()
    assert "demo" in content


def test_model_without_diff_stops_safely(workspace, config: AIConfig):
    llm = MockLLMAdapter([rationale_response("I do not think a change is needed.")])
    worker = MockWorkerClient(suites=[FAILING])

    result = repair_loop(
        "t5", workspace, llm=llm, worker=worker, audit=MockAuditClient(),
        requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.UNSAFE_PATCH
    assert "no usable unified diff" in result.note


def test_llm_failure_stops_loop(workspace, config: AIConfig):
    llm = MockLLMAdapter([])
    worker = MockWorkerClient(suites=[FAILING])

    result = repair_loop(
        "t6", workspace, llm=llm, worker=worker, audit=MockAuditClient(),
        requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.LLM_FAILURE
    assert result.success is False


def test_baseline_worker_failure(workspace, config: AIConfig):
    worker = MockWorkerClient(exceptions=[RuntimeError("terraform missing")])

    result = repair_loop(
        "t7", workspace, llm=MockLLMAdapter([]), worker=worker,
        audit=MockAuditClient(), requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.WORKER_FAILURE
    assert result.attempts == []
    assert "terraform missing" in result.note


def test_worker_failure_on_recheck(workspace, config: AIConfig):
    patch_diff = unified_replace(
        "main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"'
    )
    llm = MockLLMAdapter([tf_response(patch_diff)])
    worker = MockWorkerClient(
        suites=[FAILING],
        exceptions=[None, RuntimeError("check crashed after patch")],
    )

    result = repair_loop(
        "t8", workspace, llm=llm, worker=worker, audit=MockAuditClient(),
        requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.WORKER_FAILURE
    assert len(result.attempts) == 1
    assert result.attempts[0].applied is True
    assert "crashed after patch" in result.note


def test_regression_stops_loop(workspace, config: AIConfig):
    baseline = [
        make_check("fmt", CheckStatus.PASSED),
        make_check("validate", CheckStatus.FAILED, exit_code=1),
    ]
    after = [
        make_check("fmt", CheckStatus.FAILED, exit_code=3),
        make_check("validate", CheckStatus.PASSED),
    ]
    patch_diff = unified_replace(
        "main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"'
    )
    llm = MockLLMAdapter([tf_response(patch_diff)])
    worker = MockWorkerClient(suites=[baseline, after])

    result = repair_loop(
        "t9", workspace, llm=llm, worker=worker, audit=MockAuditClient(),
        requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.REGRESSION
    assert result.success is False
    assert len(result.attempts) == 1
    assert len(worker.check_calls) == 2


def test_intent_violated_stops_before_patching(workspace, config: AIConfig):
    llm = MockLLMAdapter([])

    def violate(requirements, diff, plan):
        return [make_requirement("bucket deleted", status="Violated")]

    result = repair_loop(
        "t10", workspace, llm=llm, worker=MockWorkerClient(suites=[PASSING]),
        audit=MockAuditClient(intent_fn=violate), requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.INTENT_VIOLATED
    assert result.success is False
    assert result.attempts == []
    assert llm.requests == []


def test_audit_failure_stops_loop(workspace, config: AIConfig):
    def boom(requirements, diff, plan):
        raise RuntimeError("audit down")

    result = repair_loop(
        "t11", workspace, llm=MockLLMAdapter([]),
        worker=MockWorkerClient(suites=[PASSING]),
        audit=MockAuditClient(intent_fn=boom), requirements=[req()], config=config,
    )

    assert result.stop_reason == StopReason.AUDIT_FAILURE
    assert result.success is False


def test_goal_is_extracted_when_requirements_missing(workspace, config: AIConfig):
    llm = MockLLMAdapter([json_requirements_response([{"text": "keep bucket", "mandatory": True}])])
    result = repair_loop(
        "t12", workspace, llm=llm, worker=MockWorkerClient(suites=[PASSING]),
        audit=MockAuditClient(intent_fn=satisfied), goal="Keep the bucket", config=config,
    )
    assert result.stop_reason == StopReason.RESOLVED
    assert result.requirements[0].text == "keep bucket"
    assert len(llm.requests) == 1


def test_missing_goal_and_requirements_raises(workspace, config: AIConfig):
    with pytest.raises(ValueError):
        repair_loop(
            "t13", workspace, llm=MockLLMAdapter([]),
            worker=MockWorkerClient(), audit=MockAuditClient(), config=config,
        )


def test_diagnostics_sent_to_model_are_redacted(workspace, config: AIConfig):
    patch_diff = unified_replace(
        "main.tf", BASE_LINES, 1, '  bucket = "demo"', '  bucket = "demo-private"'
    )
    llm = MockLLMAdapter([tf_response(patch_diff)])
    worker = MockWorkerClient(suites=[SECRET_FAILING, PASSING])
    audit = MockAuditClient(intent_fn=satisfied)

    repair_loop(
        "t14", workspace, llm=llm, worker=worker, audit=audit,
        requirements=[req()], config=config,
    )

    request = llm.requests[0]
    assert "hunter2" not in request.diagnostics
    assert "AKIA1234567890ABCDEF" not in request.diagnostics
    assert "hunter2" not in request.prompt
    assert "AKIA1234567890ABCDEF" not in request.prompt
    assert "***REDACTED***" in request.diagnostics
