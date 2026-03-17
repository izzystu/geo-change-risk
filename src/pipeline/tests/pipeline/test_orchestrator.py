"""Tests for PipelineOrchestrator."""

import pytest

from georisk.pipeline.context import StepContext
from georisk.pipeline.orchestrator import PipelineError, PipelineOrchestrator
from georisk.pipeline.step import ErrorPolicy, PipelineStep, StepResult

# --- Dummy step classes for testing ---

class SuccessStep(PipelineStep):
    name = "success_step"
    error_policy = ErrorPolicy.REQUIRED

    def execute(self, ctx: StepContext) -> StepResult:
        return StepResult(success=True, message="done")


class FailingRequiredStep(PipelineStep):
    name = "failing_required"
    error_policy = ErrorPolicy.REQUIRED

    def execute(self, ctx: StepContext) -> StepResult:
        raise ValueError("something broke")


class FailingOptionalStep(PipelineStep):
    name = "failing_optional"
    error_policy = ErrorPolicy.OPTIONAL

    def execute(self, ctx: StepContext) -> StepResult:
        raise ValueError("non-critical failure")


class ReturnFailureRequiredStep(PipelineStep):
    """Returns StepResult(success=False) instead of raising."""
    name = "return_failure_required"
    error_policy = ErrorPolicy.REQUIRED

    def execute(self, ctx: StepContext) -> StepResult:
        return StepResult(success=False, message="could not complete")


class SkippableStep(PipelineStep):
    name = "skippable_step"
    error_policy = ErrorPolicy.OPTIONAL

    def should_skip(self, ctx: StepContext) -> str | None:
        if ctx.dry_run:
            return "dry run"
        return None

    def execute(self, ctx: StepContext) -> StepResult:
        return StepResult(success=True, message="executed")


class TrackingStep(PipelineStep):
    """Records that it was executed, for order verification."""
    error_policy = ErrorPolicy.REQUIRED

    def __init__(self, step_name: str, execution_log: list):
        self.name = step_name
        self._log = execution_log

    def execute(self, ctx: StepContext) -> StepResult:
        self._log.append(self.name)
        return StepResult(success=True)


# --- Tests ---

class TestOrchestratorBasics:

    def test_runs_all_steps_in_order(self, make_context):
        log = []
        steps = [
            TrackingStep("step_a", log),
            TrackingStep("step_b", log),
            TrackingStep("step_c", log),
        ]
        orchestrator = PipelineOrchestrator(steps)
        results = orchestrator.run(make_context())

        assert log == ["step_a", "step_b", "step_c"]
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_returns_results_for_each_step(self, make_context):
        steps = [SuccessStep(), SuccessStep()]
        orchestrator = PipelineOrchestrator(steps)
        results = orchestrator.run(make_context())

        assert len(results) == 2
        assert results[0].success
        assert results[0].message == "done"


class TestRequiredStepFailure:

    def test_exception_in_required_step_raises_pipeline_error(self, make_context):
        steps = [SuccessStep(), FailingRequiredStep(), SuccessStep()]
        orchestrator = PipelineOrchestrator(steps)

        with pytest.raises(PipelineError, match="failing_required"):
            orchestrator.run(make_context())

    def test_return_failure_in_required_step_raises_pipeline_error(self, make_context):
        steps = [SuccessStep(), ReturnFailureRequiredStep()]
        orchestrator = PipelineOrchestrator(steps)

        with pytest.raises(PipelineError, match="could not complete"):
            orchestrator.run(make_context())

    def test_steps_after_required_failure_do_not_run(self, make_context):
        log = []
        steps = [
            TrackingStep("before", log),
            FailingRequiredStep(),
            TrackingStep("after", log),
        ]
        orchestrator = PipelineOrchestrator(steps)

        with pytest.raises(PipelineError):
            orchestrator.run(make_context())

        assert log == ["before"]


class TestOptionalStepFailure:

    def test_exception_in_optional_step_continues(self, make_context):
        log = []
        steps = [
            TrackingStep("before", log),
            FailingOptionalStep(),
            TrackingStep("after", log),
        ]
        orchestrator = PipelineOrchestrator(steps)
        results = orchestrator.run(make_context())

        assert log == ["before", "after"]
        assert len(results) == 3
        assert results[1].success is False
        assert results[1].error is not None


class TestSkipLogic:

    def test_skipped_step_not_executed(self, make_context):
        steps = [SkippableStep()]
        orchestrator = PipelineOrchestrator(steps)
        results = orchestrator.run(make_context(dry_run=True))

        assert len(results) == 1
        assert results[0].skipped is True
        assert results[0].skip_reason == "dry run"

    def test_non_skipped_step_executed(self, make_context):
        steps = [SkippableStep()]
        orchestrator = PipelineOrchestrator(steps)
        results = orchestrator.run(make_context(dry_run=False))

        assert len(results) == 1
        assert results[0].skipped is False
        assert results[0].message == "executed"


class TestProgressCallback:

    def test_progress_called_for_each_step(self, make_context):
        calls = []
        def on_progress(name, status, message):
            calls.append((name, status))

        steps = [SuccessStep()]
        orchestrator = PipelineOrchestrator(steps, on_progress=on_progress)
        orchestrator.run(make_context())

        assert ("success_step", "success") in calls

    def test_progress_called_on_skip(self, make_context):
        calls = []
        def on_progress(name, status, message):
            calls.append((name, status))

        steps = [SkippableStep()]
        orchestrator = PipelineOrchestrator(steps, on_progress=on_progress)
        orchestrator.run(make_context(dry_run=True))

        assert ("skippable_step", "skipped") in calls

    def test_progress_called_on_optional_error(self, make_context):
        calls = []
        def on_progress(name, status, message):
            calls.append((name, status))

        steps = [FailingOptionalStep()]
        orchestrator = PipelineOrchestrator(steps, on_progress=on_progress)
        orchestrator.run(make_context())

        assert ("failing_optional", "error") in calls
